import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from core.routers.chat import router as chat_router
from core.schemas import ModelsResponse
from core.services.ollama_service import OllamaService

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ollama = OllamaService(model=OLLAMA_MODEL)
    yield


app = FastAPI(title="Odysseus Core", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok", "model": app.state.ollama.model}


@app.get("/models", response_model=ModelsResponse)
async def list_models():
    models = await app.state.ollama.list_models()
    return ModelsResponse(models=models)
