"""Portfolio and trading: GET /api/portfolio, POST /api/portfolio/trade, GET /api/portfolio/history, POST /api/reset (PLAN.md §8)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.portfolio import execute_trade, get_history, get_portfolio, reset_portfolio

router = APIRouter()


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


@router.get("/api/portfolio")
async def portfolio(request: Request) -> dict:
    st = request.app.state
    return get_portfolio(st.db, st.price_cache)


@router.post("/api/portfolio/trade")
async def trade(body: TradeRequest, request: Request) -> dict:
    st = request.app.state
    async with st.lock:
        executed = await execute_trade(st.db, st.price_cache, st.market, body.ticker, body.side, body.quantity)
        return {"trade": executed, "portfolio": get_portfolio(st.db, st.price_cache)}


@router.get("/api/portfolio/history")
async def history(request: Request) -> dict:
    return {"snapshots": get_history(request.app.state.db)}


@router.post("/api/reset")
async def reset(request: Request) -> dict:
    st = request.app.state
    async with st.lock:
        await reset_portfolio(st.db, st.price_cache, st.market)
        return get_portfolio(st.db, st.price_cache)
