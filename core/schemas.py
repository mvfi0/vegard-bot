from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    model: str


class HistoryResponse(BaseModel):
    user_id: str
    message_count: int


class ClearResponse(BaseModel):
    cleared: bool


class ModelsResponse(BaseModel):
    models: list[str]
