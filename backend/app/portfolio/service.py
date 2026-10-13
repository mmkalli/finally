# backend/app/portfolio/service.py
"""Trade execution, portfolio valuation and watchlist changes (PLAN.md §7-8).

Everything that changes the priced set (trades, watchlist add/remove, reset) runs under `trade_lock`,
so a manual trade and an LLM trade can't race on cash, and a watchlist removal can't un-price a ticker
a trade is about to fill (MARKET_DATA_DESIGN.md §10.2). The lock is not re-entrant: callers such as
the chat module call these functions one at a time and never hold it themselves.
"""

import asyncio
import math
import sqlite3

from app import database as db
from app.errors import AppError
from app.market import (
    EMPTY_PRICE_FIELDS,
    MarketDataError,
    MarketDataSource,
    PriceCache,
    normalize_ticker,
    sync_priced_tickers,
)

trade_lock = asyncio.Lock()

POSITION_EPSILON = 1e-6


def _ticker(raw: object) -> str:
    try:
        return normalize_ticker(raw)
    except MarketDataError as e:
        raise AppError(e.code, str(e), e.http_status) from e


async def _ensure_priced(source: MarketDataSource, ticker: str) -> None:
    try:
        await source.add_ticker(ticker)
    except MarketDataError as e:
        raise AppError(e.code, str(e), e.http_status) from e


# --- portfolio ----------------------------------------------------------------------------------


def _position_view(pos: dict, cache: PriceCache) -> dict:
    qty, avg = pos["quantity"], pos["avg_cost"]
    price = cache.get_price(pos["ticker"])
    if price is None:
        price = avg  # PLAN.md §8: fall back to avg_cost while unpriced
    return {
        "ticker": pos["ticker"],
        "quantity": round(qty, 4),
        "avg_cost": round(avg, 2),
        "current_price": round(price, 2),
        "market_value": round(qty * price, 2),
        "unrealized_pnl": round((price - avg) * qty, 2),
        "pnl_percent": round((price - avg) / avg * 100, 2) if avg else 0.0,
    }


def get_portfolio(conn: sqlite3.Connection, cache: PriceCache) -> dict:
    """PLAN.md §8 `GET /api/portfolio` shape."""
    cash = db.get_cash(conn)
    positions = [_position_view(p, cache) for p in db.list_positions(conn)]
    positions_value = sum((p["market_value"] for p in positions), 0.0)
    return {
        "cash_balance": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(cash + positions_value, 2),
        "unrealized_pnl": round(sum((p["unrealized_pnl"] for p in positions), 0.0), 2),
        "positions": positions,
    }


def record_snapshot(conn: sqlite3.Connection, cache: PriceCache) -> None:
    """Insert a portfolio_snapshots row. Joins the caller's transaction if one is open."""
    with db.transaction(conn):
        db.insert_snapshot(conn, get_portfolio(conn, cache)["total_value"])


# --- trades -------------------------------------------------------------------------------------


def _check_shares(conn: sqlite3.Connection, ticker: str, quantity: float) -> None:
    pos = db.get_position(conn, ticker)
    held = pos["quantity"] if pos else 0.0
    if quantity > held + 1e-9:
        raise AppError("INSUFFICIENT_SHARES", f"Insufficient shares: you hold {held:g} {ticker}")


def _apply_trade(conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float) -> dict:
    """Validate and write one trade. Caller holds the transaction."""
    cash = db.get_cash(conn)
    pos = db.get_position(conn, ticker)
    held = pos["quantity"] if pos else 0.0

    if side == "buy":
        cost = quantity * price
        if cost > cash:
            raise AppError("INSUFFICIENT_CASH", f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}")
        new_qty = round(held + quantity, 4)
        avg = (held * pos["avg_cost"] + quantity * price) / new_qty if pos else price
        db.set_cash(conn, round(cash - cost, 2))
        db.upsert_position(conn, ticker, new_qty, avg)
    else:
        _check_shares(conn, ticker, quantity)
        remaining = round(held - quantity, 4)
        db.set_cash(conn, round(cash + quantity * price, 2))
        if remaining < POSITION_EPSILON:
            db.delete_position(conn, ticker)
        else:
            db.upsert_position(conn, ticker, remaining, pos["avg_cost"])

    return db.insert_trade(conn, ticker, side, quantity, price)


async def execute_trade(
    conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, ticker: str, side: str, quantity: float
) -> dict:
    """Market order at the cached price (PLAN.md §7). Returns the trade dict; raises AppError."""
    ticker = _ticker(ticker)
    side = side.strip().lower() if isinstance(side, str) else ""
    if side not in ("buy", "sell"):
        raise AppError("INVALID_SIDE", f"Invalid side: {side!r} (expected 'buy' or 'sell')")
    try:
        quantity = round(float(quantity), 4)
    except (TypeError, ValueError):
        raise AppError("INVALID_QUANTITY", f"Invalid quantity: {quantity!r}") from None
    if not math.isfinite(quantity) or quantity <= 0:
        raise AppError("INVALID_QUANTITY", "Quantity must be greater than 0")

    async with trade_lock:
        if side == "sell":
            _check_shares(conn, ticker, quantity)  # before NO_PRICE: selling what you don't hold is the real error
        try:
            await _ensure_priced(source, ticker)  # an unwatched, unheld ticker gets a price so it can fill
            price = cache.get_price(ticker)
            if price is None:
                raise AppError("NO_PRICE", f"No price available yet for {ticker}")
            with db.transaction(conn):
                trade = _apply_trade(conn, ticker, side, quantity, price)
                record_snapshot(conn, cache)
        finally:
            await sync_priced_tickers(conn, source)  # drops it again if the trade failed or fully sold
    return trade


# --- watchlist ----------------------------------------------------------------------------------


def watchlist_entry(cache: PriceCache, ticker: str) -> dict:
    update = cache.get(ticker)
    return update.to_dict() if update else {"ticker": ticker, **EMPTY_PRICE_FIELDS}


def list_watchlist_entries(conn: sqlite3.Connection, cache: PriceCache) -> list[dict]:
    return [watchlist_entry(cache, t) for t in db.list_watchlist(conn)]


async def add_to_watchlist(conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, ticker) -> dict:
    """Idempotent: adding a watched ticker returns its entry. Raises AppError INVALID_/UNKNOWN_TICKER."""
    ticker = _ticker(ticker)
    async with trade_lock:
        try:
            await _ensure_priced(source, ticker)  # Massive: UnknownTickerError -> nothing written
            with db.transaction(conn):
                db.add_watchlist(conn, ticker)
        finally:
            await sync_priced_tickers(conn, source)
    return watchlist_entry(cache, ticker)


async def remove_from_watchlist(conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, ticker) -> None:
    """Raises AppError NOT_FOUND if not watched. A held ticker stays priced."""
    ticker = _ticker(ticker)
    async with trade_lock:
        with db.transaction(conn):
            removed = db.remove_watchlist(conn, ticker)
        if not removed:
            raise AppError("NOT_FOUND", f"{ticker} is not on the watchlist", 404)
        await sync_priced_tickers(conn, source)


# --- reset --------------------------------------------------------------------------------------


async def reset_portfolio(conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource) -> dict:
    """Back to the seed state (PLAN.md §8 `POST /api/reset`). Returns the fresh portfolio."""
    async with trade_lock:
        with db.transaction(conn):
            db.reset_user(conn)
            record_snapshot(conn, cache)  # $10,000 starting point so the P&L chart is never empty
        await sync_priced_tickers(conn, source)
    return get_portfolio(conn, cache)
