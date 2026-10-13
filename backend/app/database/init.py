import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from importlib import resources

from app.market.models import format_timestamp

from .connection import DEFAULT_USER, utc_now

DEFAULT_CASH = 10000.0
DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

# Tables cleared by reset_to_seed (users_profile is restored rather than cleared)
USER_DATA_TABLES = ("watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages")


def init_db(conn: sqlite3.Connection) -> None:
    """Create any missing tables and seed the default user. Safe to run on every startup.

    The watchlist is seeded only together with a new user profile, so a user who removed
    every ticker doesn't get the defaults back on restart.
    """
    conn.executescript(resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8"))
    with conn:
        if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER,)).fetchone() is None:
            _seed(conn, DEFAULT_USER)


def reset_to_seed(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> None:
    """POST /api/reset: clear positions, trades, snapshots and chat; restore cash and the default watchlist.

    Runs in one transaction. The caller holds app.state.lock and re-syncs the priced tickers afterwards.
    """
    with conn:
        for table in USER_DATA_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users_profile WHERE id = ?", (user_id,))
        _seed(conn, user_id)


def _seed(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (user_id, DEFAULT_CASH, utc_now()),
    )
    # Distinct added_at values keep the default order when the watchlist is sorted by added_at
    base = datetime.now(timezone.utc)
    conn.executemany(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [
            (str(uuid.uuid4()), user_id, ticker, format_timestamp(base + timedelta(milliseconds=i)))
            for i, ticker in enumerate(DEFAULT_WATCHLIST)
        ],
    )
