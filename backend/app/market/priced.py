# backend/app/market/priced.py
import sqlite3

from .interface import MarketDataSource


def load_priced_tickers(conn: sqlite3.Connection, user_id: str = "default") -> set[str]:
    """Watchlist ∪ open positions (PLAN.md §6 'Which Tickers Are Priced')."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? UNION SELECT ticker FROM positions WHERE user_id = ?",
        (user_id, user_id),
    ).fetchall()
    return {row[0] for row in rows}


async def sync_priced_tickers(conn: sqlite3.Connection, source: MarketDataSource, user_id: str = "default") -> None:
    await source.sync(load_priced_tickers(conn, user_id))
