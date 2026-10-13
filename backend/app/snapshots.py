"""Portfolio value snapshots for the P&L chart (PLAN.md §7 portfolio_snapshots)."""
import asyncio
import logging
import sqlite3
import uuid

from app.database import DEFAULT_USER, utc_now
from app.market import PriceCache

log = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0


def compute_total_value(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> float:
    """Cash + market value of every position. An unpriced position is valued at avg_cost (PLAN.md §8)."""
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    cash = row[0] if row else 0.0
    positions = conn.execute("SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ?", (user_id,))
    value = 0.0
    for ticker, quantity, avg_cost in positions:
        price = cache.get_price(ticker)
        value += quantity * (price if price is not None else avg_cost)
    return round(cash + value, 2)


def record_snapshot(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> float:
    """Insert one snapshot and return its value.

    Does not commit: the trade path calls it inside its own transaction; standalone callers wrap it in `with conn:`.
    """
    total = compute_total_value(conn, cache, user_id)
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, total, utc_now()),
    )
    return total


async def run_snapshot_loop(
    conn: sqlite3.Connection,
    cache: PriceCache,
    lock: asyncio.Lock,
    interval: float = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Record a snapshot now and then every `interval` seconds until cancelled."""
    while True:
        try:
            async with lock:  # don't value the portfolio halfway through a trade
                with conn:
                    record_snapshot(conn, cache)
        except sqlite3.Error:
            log.exception("Portfolio snapshot failed")
        await asyncio.sleep(interval)
