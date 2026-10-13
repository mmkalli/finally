"""Watchlist: GET /api/watchlist, POST /api/watchlist, DELETE /api/watchlist/{ticker} (PLAN.md §8)."""
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.watchlist import add_to_watchlist, list_watchlist, remove_from_watchlist

router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str


@router.get("/api/watchlist")
async def get_watchlist(request: Request) -> dict:
    st = request.app.state
    return {"tickers": list_watchlist(st.db, st.price_cache)}


@router.post("/api/watchlist")
async def add_ticker(body: AddTickerRequest, request: Request) -> dict:
    st = request.app.state
    async with st.lock:
        return await add_to_watchlist(st.db, st.price_cache, st.market, body.ticker)


@router.delete("/api/watchlist/{ticker}", status_code=204)
async def remove_ticker(ticker: str, request: Request) -> Response:
    st = request.app.state
    async with st.lock:
        await remove_from_watchlist(st.db, st.market, ticker)
    return Response(status_code=204)
