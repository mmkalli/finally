"""Watchlist operations shared by the REST routes (app/api/watchlist.py) and chat actions (PLAN.md §8, §9).

The functions that change the watchlist do not take the lock themselves: the caller holds
app.state.lock (asyncio.Lock is not re-entrant, and chat runs several actions under one hold).
"""
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from app.database import DEFAULT_USER
from app.errors import AppError
from app.market import EMPTY_PRICE_FIELDS, MarketDataSource, PriceCache, normalize_ticker, sync_priced_tickers
from app.market.models import format_timestamp


def watch_entry(cache: PriceCache, ticker: str) -> dict:
    """One watchlist entry; price fields are null until the ticker has a cached price."""
    update = cache.get(ticker)
    return update.to_dict() if update else {"ticker": ticker, **EMPTY_PRICE_FIELDS}


def watched_tickers(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[str]:
    """Watchlist tickers in the order they were added."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker", (user_id,)
    ).fetchall()
    return [row[0] for row in rows]


def list_watchlist(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> list[dict]:
    return [watch_entry(cache, ticker) for ticker in watched_tickers(conn, user_id)]


def _next_added_at(conn: sqlite3.Connection, user_id: str) -> str:
    """Now, or 1 ms after the newest entry if that is later, so a new ticker always sorts last.

    The seed spaces its rows 1 ms apart from startup, so an add right after a reset could otherwise tie or sort early.
    """
    now = datetime.now(timezone.utc)
    (latest,) = conn.execute("SELECT max(added_at) FROM watchlist WHERE user_id = ?", (user_id,)).fetchone()
    if latest:
        now = max(now, datetime.fromisoformat(latest) + timedelta(milliseconds=1))
    return format_timestamp(now)


async def add_to_watchlist(
    conn: sqlite3.Connection,
    cache: PriceCache,
    market: MarketDataSource,
    raw_ticker: object,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Watch a ticker and return its entry. Idempotent: an already-watched ticker returns its entry.

    Raises InvalidTickerError (INVALID_TICKER) or UnknownTickerError (UNKNOWN_TICKER, Massive only);
    nothing is written in either case. Caller holds app.state.lock.
    """
    ticker = normalize_ticker(raw_ticker)
    if ticker in watched_tickers(conn, user_id):
        return watch_entry(cache, ticker)
    await market.add_ticker(ticker)  # validates with Massive and primes the cache before the row exists
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, ticker, _next_added_at(conn, user_id)),
            )
    except sqlite3.Error:
        await sync_priced_tickers(conn, market, user_id)  # don't keep pricing a ticker we failed to watch
        raise
    return watch_entry(cache, ticker)


async def remove_from_watchlist(
    conn: sqlite3.Connection,
    market: MarketDataSource,
    raw_ticker: object,
    user_id: str = DEFAULT_USER,
) -> str:
    """Stop watching a ticker and return it. It stays priced while it is still held (PLAN.md §6).

    Raises InvalidTickerError (INVALID_TICKER) or AppError NOT_FOUND. Caller holds app.state.lock.
    """
    ticker = normalize_ticker(raw_ticker)
    with conn:
        deleted = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        ).rowcount
    if not deleted:
        raise AppError("NOT_FOUND", f"{ticker} is not on the watchlist")
    await sync_priced_tickers(conn, market, user_id)
    return ticker
