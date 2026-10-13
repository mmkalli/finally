"""AI chat: POST /api/chat (PLAN.md §8, §9)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.chat import handle_chat
from app.errors import AppError

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> dict:
    message = body.message.strip()
    if not message:
        raise AppError("INVALID_REQUEST", "message: must not be empty")
    st = request.app.state
    return await handle_chat(st.db, st.price_cache, st.market, st.lock, message)
