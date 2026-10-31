from pathlib import Path

from pydantic import BaseModel, Field

import secrets
import base64
import os
import io
from uuid import uuid4

from openai import OpenAI

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
 
from .config import settings
from .agent import graph

ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(title = "Client Agent API", version = '1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins = settings.allowed_origins.split(','),
    allow_methods = ['GET','POST'],
    allow_headers = ['Authorization', 'Content-Type']
)
app.mount('/static',StaticFiles(directory = ROOT/'static'),name = 'static')

class ChatRequests(BaseModel):
    message : str = Field(min_length = 1, max_length = 4000)
    image_data : str | None
    history : list[dict[str,str]] = Field(default_factory = list, max_length =10)

def auth(authorization : str | None):
    if settings.api_token and not secrets.compare_digest(authorization or '',f'Bearer {settings.api_token}'):
        raise HTTPException(status_code = 401, detail = 'Invalid API')

def inspect_image(data):
    if not data:
        return ''
    
    try:
       header, payload = data.split(',',1) #data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD... [Base 64 String]
       mime = header.split(';')[0].split(':')[1]
       raw = base64.b64decode(payload, validate = True)
       if mime not in ('image/jpeg','image/png','image/webp') and len(raw) > 5_000_000:
           raise ValueError('Only JPEG/PNG/WebP under 5MB supported')
    
    except (ValueError,IndexError) as exc:
        raise HTTPException(status_code=400,detail=f'Invalid image: {exc}')
        
    client = OpenAI(api_key = settings.openai_api_key,timeout = 45)
    response = client.chat.completions.create(model = settings.openai_vision_model, 
                                  messages=[
                                                {
                                                    'role': 'user', 
                                                    'content': [
                                                        {'type': 'text', 'text': 'Describe only objectively visible medical-relevant features. Do not diagnose, estimate severity, or assert absence of illness. If image unclear, say so.'},
                                                        {'type': 'image_url', 'image_url': {'url': data}}
                                                    ]
                                                }
                                            ], 
                                  max_tokens = 300)
    
    return response.choices[0].message.content

# END Point

@app.get('/',response_class = HTMLResponse)
def home():
    return (ROOT/'templates'/'index.html').read_text(encoding = 'utf-8')

@app.get('/api/health')
def health():
    return {'status' : 'ok', 'configured' : bool(settings.openai_api_key and settings.pinecone_api_key) ,'tavily' : bool(settings.tavily_api_key)}

@app.post('/api/chat')
def chat(
    payload : ChatRequests,
    authorization : str | None = Header(default = None),
    conversation_id : str | None = Header(default = None, alias = 'X-Conversation-ID')
    
):
    auth(authorization)
    
    if not settings.openai_api_key or not settings.pinecone_api_key:
        raise HTTPException(status_code=503, detail = 'Set OPENAI_API_KEY and PINECONE_API_KEY in .env')
    
    history = [x for x in payload.history if x.get('role') in ('user','assistant') and isinstance(x.get('content'),str)][:10]
    
    thread_id = conversation_id or str(uuid4())
    config = {'configurable' : {'thread_id' : thread_id}}
    
    try:
        observation  = inspect_image(payload.image_data)
        
        state = graph.invoke(
            {
                    'question':payload.message,
                    'history':history,
                    'image_description':observation,
                    'kb':[],
                    'web':[],
                    'answer':'',
                    'route':''
                },
                config=config
            
        )
        return {
            'answer' : state['answer'],
            'tools': ['Pinecone'] + (['Tavily'] if state['route'] == 'web' and settings.tavily_api_key else []) + (['Vision'] if observation else []),
            'source' : [{'type':'pdf', 'page': i['metadata']['page'] , 'score' : i['score']} for i in state['kb']] + [{'type':'web', 'url': j['url'],'title': j['title']} for j in state['web']],
            'consversation_id' : thread_id
        
        }
    except HTTPException:
        raise 
    except Exception as exc:
        print('Chat error:',repr(exc),flush=True)
        raise HTTPException(502,'AI service failed. Check server logs, credentials, Pinecone index, and connectivity.')

@app.post('/api/transcribe')
#Incoming Audio file stroe in Temp RAM
async def transcribe(file : UploadFile = File(...), authorization : str | None = Header(default = None)):
    auth(authorization)
    
    data = await file.read(10_000_001) # Read from ram upto 10 MB 1 byte
    if len(data) > 10_000_000:
        raise HTTPException(status_code = 413,detail = 'Audio exceeds 10 MB')
        
    if not data:
        raise HTTPException(status_code=400, detail='Audio file is empty')
    if len(data) < 256:
        raise HTTPException(
            status_code=400,
            detail='No usable audio was captured. Speak clearly and try again.',
        )

    audio = io.BytesIO(data) # store in virtual container for reading
    audio.name = Path(file.filename or 'voice.webm').name
    print(
        f'Transcription upload: filename={audio.name!r}, '
        f'content_type={file.content_type!r}, bytes={len(data)}',
        flush=True,
    )
    try:
        client = OpenAI(api_key= settings.openai_api_key)
        transcription = client.audio.transcriptions.create(model = 'whisper-1', file = audio)
        return {'text': transcription.text}
    except Exception as exc:
        print('Transcription error:', repr(exc), flush=True)
        raise HTTPException(status_code = 502, detail = 'Speech transcription unavailable')
   
@app.post('/api/speech')
def speech(payload : dict, authorization : str | None = Header(default = None)):
    
    auth(authorization)
    
    text = str(payload.get('text',''))[:3000]
    if not text:
        raise HTTPException(status_code = 400, detail = 'missing text')
    try:
        client = OpenAI(api_key = settings.openai_api_key)
        audio = client.audio.speech.create(model = 'tts-1', voice= 'alloy', input = text)
        
        return Response(content = audio.content, media_type = 'audio/mpeg')
    except Exception as exc:
        print('Speech synthesis error:', repr(exc), flush=True)
        raise HTTPException(status_code = 503, detail = 'Speech synthesis unavailable')
    

"""

def get_image_data_url(file_path):
    if file_path.endswith(".png"):
        mime = "image/png"
    elif file_path.endswith(".webp"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        
    return f"data:{mime};base64,{encoded}"

if __name__ == "__main__":
    image_filename = "/Users/anushbharathwaj/Downloads/IMG_7271.PNG"
    
    if not os.path.exists(image_filename):
        print(f"Error: Could not find '{image_filename}' in this folder. Please add a test image.")
        exit(1)

    print(f"Converting '{image_filename}' to Data URL...")
    data_url = get_image_data_url(image_filename)

    print("Calling inspect_image() function with OpenAI API...")
    try:
        api_response = inspect_image(data_url)
        
        print("\nSUCCESS. Raw API Response Object:")
        print(api_response)
        
        print("\nExtracted AI Text Content:")
        print(api_response.choices[0].message.content)
        
    except Exception as e:
        print(f"\nFAILED: {e}")

"""

#print(ROOT) 