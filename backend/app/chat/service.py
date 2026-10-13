"""POST /api/chat orchestration: context -> one LLM call -> execute actions -> persist (PLAN.md §9)."""

from __future__ import annotations

import logging
import os

from app.database import insert_chat_message, list_watchlist, recent_chat_messages, transaction
from app.errors import AppError
from app.market.models import EMPTY_PRICE_FIELDS
from app.market.tickers import MarketDataError
from app.portfolio.service import add_to_watchlist, execute_trade, get_portfolio, remove_from_watchlist

from . import llm
from .mock import mock_response
from .models import ChatResponse, TradeRequest, WatchlistChange
from .prompt import build_messages

log = logging.getLogger(__name__)

NOT_CONFIGURED_MESSAGE = "AI chat isn't configured — set OPENROUTER_API_KEY in .env to enable it."
UNAVAILABLE_MESSAGE = "Sorry, I couldn't reach the AI service just now. Please try again."
HISTORY_LIMIT = 20


def mock_enabled() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def api_key_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


async def handle_chat(conn, cache, source, message: str) -> dict:
    if mock_enabled():
        response = mock_response(message)
    elif not api_key_configured():
        response = ChatResponse(message=NOT_CONFIGURED_MESSAGE, trades=[], watchlist_changes=[])
    else:
        response = await _ask_llm(conn, cache, message)

    actions = []
    for trade in response.trades:
        actions.append(await _run_trade(conn, cache, source, trade))
    for change in response.watchlist_changes:
        actions.append(await _run_watchlist_change(conn, cache, source, change))

    with transaction(conn):
        insert_chat_message(conn, "user", message, None)
        insert_chat_message(conn, "assistant", response.message, actions)

    return {"message": response.message, "actions": actions}


async def _ask_llm(conn, cache, message: str) -> ChatResponse:
    portfolio = get_portfolio(conn, cache)
    watchlist = [_watchlist_entry(cache, t) for t in list_watchlist(conn)]
    history = recent_chat_messages(conn, limit=HISTORY_LIMIT)
    messages = build_messages(portfolio, watchlist, history, message)
    try:
        raw = await llm.call_llm(messages)
    except Exception:
        log.exception("LLM call failed")
        return ChatResponse(message=UNAVAILABLE_MESSAGE, trades=[], watchlist_changes=[])
    return llm.parse_response(raw)


def _watchlist_entry(cache, ticker: str) -> dict:
    update = cache.get(ticker)
    return update.to_dict() if update else {"ticker": ticker, **EMPTY_PRICE_FIELDS}


async def _run_trade(conn, cache, source, trade: TradeRequest) -> dict:
    action = {"type": "trade", "ticker": trade.ticker.strip().upper(), "side": trade.side, "quantity": trade.quantity}
    try:
        result = await execute_trade(conn, cache, source, trade.ticker, trade.side, trade.quantity)
    except Exception as exc:
        return {**action, **_error_fields(exc)}
    return {
        **action,
        "ticker": result["ticker"],
        "quantity": result["quantity"],
        "price": result["price"],
        "status": "ok",
    }


async def _run_watchlist_change(conn, cache, source, change: WatchlistChange) -> dict:
    action = {"type": "watchlist", "ticker": change.ticker.strip().upper(), "action": change.action}
    try:
        if change.action == "add":
            entry = await add_to_watchlist(conn, cache, source, change.ticker)
            action["ticker"] = entry["ticker"]
        else:
            await remove_from_watchlist(conn, cache, source, change.ticker)
    except Exception as exc:
        return {**action, **_error_fields(exc)}
    return {**action, "status": "ok"}


def _error_fields(exc: Exception) -> dict:
    """A failed action is reported inline and never aborts the remaining actions (PLAN.md §8)."""
    if isinstance(exc, AppError):
        return {"status": "error", "error": exc.message, "code": exc.code}
    if isinstance(exc, MarketDataError):
        return {"status": "error", "error": str(exc), "code": exc.code}
    log.exception("Unexpected error executing chat action")
    return {"status": "error", "error": "Unexpected error executing this action", "code": "INTERNAL_ERROR"}
