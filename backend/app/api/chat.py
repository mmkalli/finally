# backend/app/api/chat.py
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.errors import AppError

router = APIRouter()


class ChatRequest(BaseModel):
    message: Any = None


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict:
    from app.chat import handle_chat  # owned by the llm engineer; imported lazily so the app starts without it

    if not isinstance(body.message, str) or not body.message.strip():
        raise AppError("INVALID_REQUEST", "Message must be a non-empty string")
    st = request.app.state
    return await handle_chat(st.conn, st.cache, st.source, body.message.strip())
