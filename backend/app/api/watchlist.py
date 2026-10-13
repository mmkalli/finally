# backend/app/api/watchlist.py
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.portfolio import add_to_watchlist, list_watchlist_entries, remove_from_watchlist

router = APIRouter()


class WatchlistAdd(BaseModel):
    ticker: Any = None  # validated by the service (INVALID_TICKER)


@router.get("/watchlist")
async def get_watchlist(request: Request) -> dict:
    st = request.app.state
    return {"tickers": list_watchlist_entries(st.conn, st.cache)}


@router.post("/watchlist")
async def add(body: WatchlistAdd, request: Request) -> dict:
    st = request.app.state
    return await add_to_watchlist(st.conn, st.cache, st.source, body.ticker)


@router.delete("/watchlist/{ticker}", status_code=204)
async def remove(ticker: str, request: Request) -> Response:
    st = request.app.state
    await remove_from_watchlist(st.conn, st.cache, st.source, ticker)
    return Response(status_code=204)
