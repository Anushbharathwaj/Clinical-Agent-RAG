import argparse
import pymupdf as fitz
import hashlib
from pathlib import Path
from app.knowledge import embed,ensure_index

def chunks(text, size = 1100, overlap = 180):
    text = ' '.join(text.split())
    step = size - overlap
    return [text[i: i+size] for i in range(0,len(text),step) if len(text[i : i+size])> 100]

def main():
   
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', default = 'data/Medical_book.pdf')
    args = parser.parse_args()
    
    pdf = Path(args.pdf)
    
    if not pdf:
        raise SystemExit('PDF not found{pdf}')

    index = ensure_index()
    
    with fitz.open(pdf) as doc:
        batch = []
        for page_number,page in enumerate(doc,1):
            print(f"Reading page {page_number}...", flush=True)
            for part,content in enumerate(chunks(page.get_text()),1):
                key = hashlib.sha256(f'{pdf.name}:{page_number}:{part}:{content}'.encode()).hexdigest()
                batch.append((key,content,{'page':page_number,'text': content, 'file' : pdf.name}))
                if len(batch) >= 50:
                    print("Uploading batch of 50 to Pinecone...", flush=True)
                    vectors = embed([b[1] for b in batch])
                    index.upsert(vectors=[{'id':b[0],'values':v, 'metadata':b[2]} for b,v in zip(batch,vectors)])
                    batch=[]
                
            if page_number % 50 == 0:
                print(f'Indexed Page {page_number}/{len(doc)}',flush= True)
                
        if batch:
            vectors = embed([b[1] for b in batch])
            index.upsert(vectors=[{'id':b[0],'values':v,'metadata':b[2]} for b,v in zip(batch,vectors)])
            
if __name__ == '__main__':
    main()

# Sample medical text for testing
#sample_medical_text = """
#Patient is a 45-year-id male presenting with persistent chest discomfort, shortness of breath upon exertion, and mild palpitations over the past two weeks. The symptoms began gradually and have shown no significant improvement with rest. Past medical history is notable for essential hypertension diagnosed five years ago, currently managed with lisinopril 10mg daily, and type 2 diabetes mellitus well-controlled on metformin 500mg twice daily. There is no known family history of premature coronary artery disease or sudden cardiac death. The patient denies any recent travel, trauma, or prolonged immobilization. 
#Physical examination reveals a well-developed, well-nourished individual in no acute distress. Vital signs show a blood pressure of 134/86 mmHg, heart rate of 78 beats per minute, respiratory rate of 16 breaths per minute, and oxygen saturation at 98 percent on ambient air. Cardiac auscultation demonstrates a regular rate and rhythm with normal S1 and S2 heart sounds; no murmurs, gallops, or friction rubs are appreciated. Lungs are clear to auscultation bilaterally with good air entry and no wheezes, rales, or rhonchi. Abdomen is soft, non-tender, and non-distended with active bowel sounds. Extremities show no peripheral edema, cyanosis, or clubbing, and peripheral pulses are intact and symmetrical throughout. 

#Initial diagnostic workup includes a standard 12-lead electrocardiogram, which reveals normal sinus rhythm with no acute ST-segment or T-wave abnormalities indicative of ischemia. A complete blood count and comprehensive metabolic panel are ordered to assess baseline organ function and electrolyte balance. Cardiac biomarker testing, including high-sensitivity troponin, is pending. The patient is advised to avoid strenuous physical activity, maintain a low-sodium diet, and monitor blood pressure twice daily. A follow-up appointment is scheduled in 48 hours to review laboratory results and determine the next steps in management, which may include outpatient stress testing if symptoms persist.
#"""

# Run the function
#result_chunks = chunks(sample_medical_text)

#print(len(result_chunks))
