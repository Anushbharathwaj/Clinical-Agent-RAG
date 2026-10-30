from functools import lru_cache
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from .config import settings

@lru_cache
def clients():
    if not settings.openai_api_key and not settings.pinecone_api_key:
        raise ValueError("OpenAI and Pinecone API keys must be set in the environment variables.")
    return OpenAI(api_key = settings.openai_api_key), Pinecone(api_key=settings.pinecone_api_key)

# Create Index and Load Index (Vector)

def ensure_index():
    o,p = clients()
    if not p.has_index(settings.pinecone_index):
        p.create_index(name = settings.pinecone_index, dimension=1536,metric= 'cosine', spec =ServerlessSpec(cloud='aws', region ='us-east-1'))
    return p.Index(settings.pinecone_index) #Load Database

def embed(text):
    o,p = clients()
    return [ x.embedding for x in o.embeddings.create(input = text, model = settings.openai_embed_model).data]
    

def search(query, top_k = 5):
    index = ensure_index()
    vector = embed(query)[0]
    result = index.query(vector = vector,top_k = top_k, include_metadata= True)
    return result.get('matches',[])

# print(embed(["what is your name","How are you"])[0])

# print(search(["what is your name","How are you"]))