# Clinical-Agent-RAG
Full-stack agentic medical AI application built with LangGraph, Pinecone, and FastAPI. Features multimodal vision, voice integration, document RAG, and real-time Tavily web search.

# For Initial Setup UV

## Initialize a uv project (creates pyproject.toml and a .venv automatically)

uv init --app

## Create a virtual environment named .venv

uv venv
source .venv/bin/activate

## Add all your required packages

uv add \
  "fastapi>=0.115,<1" \
  "uvicorn[standard]>=0.30,<1" \
  "python-multipart>=0.0.9" \
  "python-dotenv>=1,<2" \
  "pydantic-settings>=2,<3" \
  "langgraph>=0.3,<2" \
  "langchain-openai>=0.3,<2" \
  "pinecone>=6,<9" \
  "tavily-python>=0.5,<1" \
  "pymupdf>=1.24,<2" \
  "certifi>=2024" \
  "openai>=1.75,<3" \
  "httpx>=0.27,<1" \
  "langgraph-checkpoint-sqlite==3.1.2"

# Run Python file to avoid relative file path
-From Root Folder

python3 -m app.agent 