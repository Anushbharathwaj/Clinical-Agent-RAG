const $ = (s) => document.querySelector(s);
const chat = $('#chat'), input = $('#input'), sendBtn = $('#send'), mic = $('#mic');

const state = {
  history: [],
  convId: localStorage.getItem('conv_id') || '',
  token: '',          // memory only: gone on refresh
  tokenExpiry: 0,
  tokenTimer: null,
  image: null,
  busy: false,
  vision: false,
  stream: null,
  stopListening: null,
  cancelled: false,
  audio: null,
  audioDone: null,
  speakCtl: null,
};

const icons = () => window.lucide && lucide.createIcons();

/* ---------- API helper ---------- */
const TOKEN_TTL = 60 * 60 * 1000;   // 1 hour
localStorage.removeItem('api_token');  // clean up older versions that saved it

function expireToken(message = 'Token expired. Enter it again.') {
  clearTimeout(state.tokenTimer);
  state.token = ''; state.tokenExpiry = 0;
  $('#token').value = '';
  $('#tokenHint').textContent = message;
  $('#tokenHint').classList.add('warn');
}

function headers(extra = {}) {
  const h = { ...extra };
  if (state.token && Date.now() > state.tokenExpiry) expireToken();   // covers sleeping tabs
  if (state.token) h['Authorization'] = `Bearer ${state.token}`;
  return h;
}

async function errorText(res) {
  try { const j = await res.json(); return j.detail || res.statusText; }
  catch { return res.statusText; }
}

/* ---------- Health and tool status ---------- */
function setTool(id, on) {
  const el = $(id);
  el.textContent = on ? 'on' : 'off';
  el.className = on ? 'on' : 'off';
}

function setVision(on) {
  state.vision = on;
  setTool('#tVision', on);
  for (const id of ['#attach', '#camBtn']) {
    $(id).disabled = !on;
    $(id).title = on ? '' : 'Image reading is off. Add OPENAI_API_KEY on the server.';
  }
}

async function checkHealth() {
  const pill = $('#statusPill'), text = $('#statusText');
  try {
    const h = await (await fetch('/api/health')).json();
    const pinecone = h.pinecone ?? h.configured;   // older backend only sends "configured"
    const vision = h.vision ?? Boolean(h.configured);
    setTool('#tKb', pinecone);
    setTool('#tWeb', h.tavily);
    setVision(vision);
    pill.dataset.state = h.configured ? 'online' : 'setup';
    text.textContent = h.configured ? 'Live' : 'Add API keys in .env';
  } catch {
    setTool('#tKb', false); setTool('#tWeb', false); setVision(false);
    pill.dataset.state = 'offline';
    text.textContent = 'Server offline';
  }
}

/* ---------- Rendering ---------- */
function render(md) {
  return DOMPurify.sanitize(marked.parse(md, { breaks: true }));
}

function hideEmpty() { const e = $('#empty'); if (e) e.remove(); }
function scrollDown() { chat.scrollTop = chat.scrollHeight; }

function addUser(text, img) {
  hideEmpty();
  const el = document.createElement('div');
  el.className = 'msg user';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (img) { const i = document.createElement('img'); i.className = 'thumb'; i.src = img; bubble.append(i); }
  const p = document.createElement('div'); p.textContent = text; bubble.append(p);
  el.append(bubble); chat.append(el); scrollDown();
}

function addTyping() {
  const el = document.createElement('div');
  el.className = 'msg bot';
  el.innerHTML = `<div class="bubble"><div class="thinking" role="status">
    <span class="gather"><i></i><i></i><i></i><i></i></span><span>Thinking…</span></div></div>`;
  chat.append(el); scrollDown();
  return el;
}

function fillBot(el, data) {
  const tools = (data.tools || []).map((t) => `<span class="tag">${t}</span>`).join('');
  const seen = new Set();
  const sources = (data.source || []).map((s) => {
    if (s.type === 'pdf') {
      const k = `p${s.page}`; if (seen.has(k)) return ''; seen.add(k);
      return `<span class="src">Book p.${s.page}</span>`;
    }
    const title = (s.title || s.url).replace(/[<>&"]/g, '');
    return `<a class="src" href="${encodeURI(s.url)}" target="_blank" rel="noopener noreferrer">${title}</a>`;
  }).join('');
  el.innerHTML = `
    <div class="bubble">${render(data.answer)}</div>
    <div class="meta">${tools}${sources}
      <button class="speak" aria-label="Read aloud"><i data-lucide="volume-2"></i>Listen</button>
    </div>`;
  el.querySelector('.speak').onclick = () => speak(data.answer);
  icons(); scrollDown();
}

function addError(el, msg) {
  el.className = 'msg bot error';
  el.innerHTML = `<div class="bubble"></div>`;
  el.querySelector('.bubble').textContent = msg;
  scrollDown();
}

/* ---------- Chat ---------- */
async function send(text) {
  text = (text ?? input.value).trim();
  if (!text || state.busy) return null;

  state.busy = true; sendBtn.disabled = true;
  const image = state.image;
  addUser(text, image);
  input.value = ''; autosize(); clearImage();
  const typing = addTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: headers({
        'Content-Type': 'application/json',
        ...(state.convId ? { 'X-Conversation-ID': state.convId } : {}),
      }),
      body: JSON.stringify({ message: text, image_data: image, history: state.history.slice(-10) }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    const data = await res.json();

    // backend currently returns the misspelled key "consversation_id"
    const id = data.conversation_id || data.consversation_id;
    if (id) { state.convId = id; localStorage.setItem('conv_id', id); }

    state.history.push({ role: 'user', content: text }, { role: 'assistant', content: data.answer });
    fillBot(typing, data);
    return data.answer;
  } catch (e) {
    addError(typing, `Could not get an answer: ${e.message}`);
    return null;
  } finally {
    state.busy = false; sendBtn.disabled = false;
  }
}

/* ---------- Image: attach or camera ---------- */
function setImage(url) {
  state.image = url; $('#previewImg').src = url; $('#preview').hidden = false;
}
function clearImage() {
  state.image = null; $('#preview').hidden = true; $('#file').value = '';
}
$('#attach').onclick = () => $('#file').click();
$('#removeImg').onclick = clearImage;
$('#file').onchange = (e) => {
  const f = e.target.files[0]; if (!f) return;
  if (f.size > 5_000_000) { alert('Image must be under 5 MB.'); clearImage(); return; }
  const r = new FileReader();
  r.onload = () => setImage(r.result);
  r.readAsDataURL(f);
};

const camDlg = $('#camDlg'), camVideo = $('#camVideo'), camErr = $('#camErr');
let camStream = null, camFacing = 'environment';

function stopCam() {
  camStream?.getTracks().forEach((t) => t.stop()); camStream = null; camVideo.srcObject = null;
}
async function startCam() {
  stopCam(); camErr.hidden = true;
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: camFacing, width: { ideal: 1280 } } });
    camVideo.srcObject = camStream;
  } catch (e) {
    camErr.textContent = `Camera unavailable: ${e.message}. Allow camera access in your browser and try again.`;
    camErr.hidden = false;
  }
}
$('#camBtn').onclick = () => { camDlg.showModal(); startCam(); };
$('#camClose').onclick = () => camDlg.close();
$('#camFlip').onclick = () => { camFacing = camFacing === 'environment' ? 'user' : 'environment'; startCam(); };
camDlg.onclose = stopCam;
$('#camShot').onclick = () => {
  if (!camVideo.videoWidth) return;
  const scale = Math.min(1, 1280 / camVideo.videoWidth);
  const c = document.createElement('canvas');
  c.width = camVideo.videoWidth * scale; c.height = camVideo.videoHeight * scale;
  c.getContext('2d').drawImage(camVideo, 0, 0, c.width, c.height);
  setImage(c.toDataURL('image/jpeg', 0.85));
  camDlg.close();
};

/* ---------- Voice: listen and transcribe ---------- */
function setLevel(v) { $('#level').style.width = `${Math.min(100, v * 8)}%`; }

// Records until silence (or until stopListening() is called). Resolves a Blob, or null if nothing was said.
function listen(stream) {
  return new Promise((resolve) => {
    const supportedTypes = ['audio/webm;codecs=opus', 'audio/mp4'];
    const mimeType = supportedTypes.find((type) => MediaRecorder.isTypeSupported(type));
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined), chunks = [];
    const ctx = new AudioContext();
    const an = ctx.createAnalyser(); an.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let heard = false, last = Date.now(), speechMs = 0, previousTick = last, raf;
    const start = Date.now();

    const tick = () => {
      an.getByteTimeDomainData(buf);
      const now = Date.now();
      let sumSquares = 0;
      for (const value of buf) sumSquares += (value - 128) ** 2;
      const level = Math.sqrt(sumSquares / buf.length);
      const elapsed = Math.min(now - previousTick, 100);
      previousTick = now;
      if (level > 4) {
        speechMs += elapsed;
        if (speechMs >= 150) heard = true;
        if (heard) last = now;
      } else {
        speechMs = 0;
      }
      setLevel(level);
      if ((heard && now - last > 1400) || (!heard && now - start > 12000) || now - start > 60000) {
        if (rec.state === 'recording') rec.stop();
      } else raf = requestAnimationFrame(tick);
    };

    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.onstop = () => {
      cancelAnimationFrame(raf); ctx.close(); setLevel(0); state.stopListening = null;
      resolve(heard ? new Blob(chunks, { type: rec.mimeType || 'audio/webm' }) : null);
    };
    state.stopListening = () => { if (rec.state === 'recording') rec.stop(); };
    rec.start(); tick();
  });
}

async function transcribe(blob) {
  const extensions = {
    'audio/webm': 'webm', 'audio/mp4': 'mp4', 'audio/mpeg': 'mp3',
    'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/flac': 'flac',
  };
  const mimeType = (blob.type || '').split(';', 1)[0].toLowerCase();
  const extension = extensions[mimeType];
  if (!extension) throw new Error(`Unsupported recording format: ${mimeType || 'unknown'}`);

  const fd = new FormData();
  fd.append('file', blob, `voice.${extension}`);
  const res = await fetch('/api/transcribe', { method: 'POST', headers: headers(), body: fd });
  if (!res.ok) throw new Error(await errorText(res));
  return (await res.json()).text || '';
}

async function getStream() {
  if (!state.stream) state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  return state.stream;
}
function releaseStream() {
  state.stream?.getTracks().forEach((t) => t.stop()); state.stream = null;
}

/* Mic bar: shows while the microphone is on, with Cancel and Done */
function showRec(mode) {   // 'listen' | 'work' | null
  $('#recBar').hidden = !mode; $('#row').hidden = !!mode;
  const working = mode === 'work';
  $('#recSpin').hidden = !working;
  $('#recCancel').hidden = working; $('#recDone').hidden = working;
  document.querySelector('.meter').hidden = working;
  $('#recText').textContent = working ? 'Transcribing…' : 'Microphone is on. Listening…';
}

async function dictate() {
  state.cancelled = false;
  try {
    const stream = await getStream();
    showRec('listen');
    const blob = await listen(stream);
    releaseStream();
    if (state.cancelled) { showRec(null); return; }
    if (!blob) { showRec(null); alert('No speech detected. Check your microphone and try again.'); return; }
    showRec('work');
    const text = await transcribe(blob);
    showRec(null);
    input.value = (input.value + ' ' + text).trim(); autosize(); input.focus();
  } catch (e) {
    releaseStream(); showRec(null);
    alert('Microphone problem: ' + e.message);
  }
}
mic.onclick = dictate;
$('#recDone').onclick = () => state.stopListening?.();
$('#recCancel').onclick = () => { state.cancelled = true; state.stopListening?.(); };
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && state.stopListening) { state.cancelled = true; state.stopListening(); }
});

/* ---------- Voice: read answers aloud ---------- */
function showSpeak(text) { $('#speakText').textContent = text; $('#speakBar').hidden = false; }
function hideSpeak() { $('#speakBar').hidden = true; }

async function speak(text) {
  stopSpeaking();
  const ctl = new AbortController(); state.speakCtl = ctl;
  showSpeak('Preparing voice…');
  try {
    const res = await fetch('/api/speech', {
      method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text: text.slice(0, 3000) }), signal: ctl.signal,
    });
    if (!res.ok) throw new Error(await errorText(res));
    const url = URL.createObjectURL(await res.blob());
    if (ctl.signal.aborted) { URL.revokeObjectURL(url); return; }
    const a = new Audio(url); state.audio = a;
    showSpeak('Speaking…');
    await new Promise((done) => { state.audioDone = done; a.onended = a.onerror = done; a.play().catch(done); });
    URL.revokeObjectURL(url);
  } catch (e) {
    if (e.name !== 'AbortError') {
      showSpeak('Voice unavailable: ' + e.message);
      await new Promise((r) => setTimeout(r, 2500));
    }
  } finally {
    if (state.speakCtl === ctl) { state.speakCtl = null; state.audio = null; hideSpeak(); }
  }
}

function stopSpeaking() {
  state.speakCtl?.abort(); state.speakCtl = null;
  state.audio?.pause(); state.audio = null;
  state.audioDone?.(); state.audioDone = null;
  hideSpeak();
}
$('#speakStop').onclick = stopSpeaking;

/* ---------- Misc UI ---------- */
function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; }
input.oninput = autosize;
input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
sendBtn.onclick = () => send();
document.addEventListener('click', (e) => { if (e.target.classList.contains('chip')) send(e.target.textContent); });

$('#token').value = '';
$('#token').onchange = (e) => {
  const value = e.target.value.trim();
  clearTimeout(state.tokenTimer);
  if (!value) { expireToken('Kept for 1 hour. Cleared when you refresh.'); $('#tokenHint').classList.remove('warn'); return; }
  state.token = value;
  state.tokenExpiry = Date.now() + TOKEN_TTL;
  state.tokenTimer = setTimeout(() => expireToken(), TOKEN_TTL);
  const until = new Date(state.tokenExpiry).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  $('#tokenHint').textContent = `Valid until ${until}, then enter it again.`;
  $('#tokenHint').classList.remove('warn');
  checkHealth();
};

$('#newChat').onclick = () => {
  stopSpeaking(); state.history = []; state.convId = ''; localStorage.removeItem('conv_id');
  location.reload();
};

$('#menu').onclick = () => $('#side').classList.toggle('open');
chat.onclick = () => $('#side').classList.remove('open');

icons(); checkHealth(); setInterval(checkHealth, 20000);