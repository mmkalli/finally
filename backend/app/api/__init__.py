# backend/app/api/__init__.py
from fastapi import APIRouter

from . import chat, health, portfolio, watchlist

api_router = APIRouter(prefix="/api")
for module in (health, portfolio, watchlist, chat):
    api_router.include_router(module.router)

__all__ = ["api_router"]
