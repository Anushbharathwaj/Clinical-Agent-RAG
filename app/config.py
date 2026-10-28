import os
import certifi
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
load_dotenv()

ssl_cert = os.environ.get('SSL_CERT_FILE')
if ssl_cert and not os.path.exists(ssl_cert):
    os.environ['SSL_CERT_FILE'] = certifi.where()
elif not ssl_cert:
    os.environ['SSL_CERT_FILE'] = certifi.where()


class Settings(BaseSettings):
    openai_api_key : str = '',
    pinecone_api_key : str = '',
    tavily_api_key : str = '',
    pinecone_index : str = 'clinical-agent-rag',
    openai_chat_model : str = 'gpt-4.1-mini',
    openai_embed_model : str = 'text-embedding-3-small',
    openai_vision_model : str = 'gpt-4.1-mini',
    api_token : str = '',
    allowed_origins :str = 'http://localhost:8000,http://127.0.0.1:8000',
    
    model_config = SettingsConfigDict(env_file = '.env', extra = 'ignore')
    
settings = Settings()


# print(settings.model_dump())
#print(f"OpenAI Model {settings.openai_chat_model}")