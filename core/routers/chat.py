from fastapi import APIRouter, HTTPException, Request

from core.schemas import ChatRequest, ChatResponse, ClearResponse, HistoryResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    service = request.app.state.ollama
    try:
        reply = await service.chat(body.user_id, body.message, body.context)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Model unavailable: {exc}")
    return ChatResponse(reply=reply, model=service.model)


@router.get("/{user_id}/history", response_model=HistoryResponse)
async def get_history(request: Request, user_id: str):
    service = request.app.state.ollama
    return HistoryResponse(user_id=user_id, message_count=service.history_count(user_id))


@router.delete("/{user_id}", response_model=ClearResponse)
async def clear_history(request: Request, user_id: str):
    request.app.state.ollama.clear_history(user_id)
    return ClearResponse(cleared=True)
