# backend/app/api/portfolio.py
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import database as db
from app.portfolio import execute_trade, get_portfolio, reset_portfolio

router = APIRouter()


class TradeRequest(BaseModel):
    ticker: Any = None   # validated by the service so bad values get PLAN.md §8 codes, not a 422
    quantity: Any = None
    side: Any = None


@router.get("/portfolio")
async def portfolio(request: Request) -> dict:
    st = request.app.state
    return get_portfolio(st.conn, st.cache)


@router.post("/portfolio/trade")
async def trade(body: TradeRequest, request: Request) -> dict:
    st = request.app.state
    result = await execute_trade(st.conn, st.cache, st.source, body.ticker, body.side, body.quantity)
    return {"trade": result, "portfolio": get_portfolio(st.conn, st.cache)}


@router.get("/portfolio/history")
async def history(request: Request) -> dict:
    return {"snapshots": db.list_snapshots(request.app.state.conn)}


@router.post("/reset")
async def reset(request: Request) -> dict:
    st = request.app.state
    return await reset_portfolio(st.conn, st.cache, st.source)
