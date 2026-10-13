# backend/app/api/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
