# backend/app/database/queries.py
"""Data-access functions. None of them commit — callers wrap writes in `transaction(conn)`."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .seed import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST


def now_iso() -> str:
    """Current UTC time, ISO-8601 with millisecond precision and a `Z` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_id() -> str:
    return str(uuid.uuid4())


# --- seed ---------------------------------------------------------------------------------------


def _insert_default_watchlist(conn: sqlite3.Connection, user_id: str) -> None:
    ts = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(_new_id(), user_id, t, ts) for t in DEFAULT_WATCHLIST],
    )


def seed_user_if_missing(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> bool:
    """Create the profile and default watchlist if the profile doesn't exist. Returns True if seeded.

    The watchlist is only seeded together with a new profile, so a user who emptied their
    watchlist doesn't get the defaults back on restart.
    """
    if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (user_id,)).fetchone():
        return False
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (user_id, DEFAULT_CASH, now_iso()),
    )
    _insert_default_watchlist(conn, user_id)
    return True


# --- cash ---------------------------------------------------------------------------------------


def get_cash(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> float:
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(f"no profile for user {user_id!r}")
    return row[0]


def set_cash(conn: sqlite3.Connection, amount: float, user_id: str = DEFAULT_USER_ID) -> None:
    """Set the cash balance, rounded to 2 dp."""
    conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (round(amount, 2), user_id))


# --- watchlist ----------------------------------------------------------------------------------


def list_watchlist(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[str]:
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid", (user_id,)
    ).fetchall()
    return [r[0] for r in rows]


def add_watchlist(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Add a ticker. Returns False if it was already on the watchlist."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, ticker, now_iso()),
    )
    return cur.rowcount == 1


def remove_watchlist(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Remove a ticker. Returns False if it wasn't on the watchlist."""
    cur = conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    return cur.rowcount == 1


# --- positions ----------------------------------------------------------------------------------

_POSITION_COLS = "ticker, quantity, avg_cost, updated_at"


def list_positions(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    rows = conn.execute(
        f"SELECT {_POSITION_COLS} FROM positions WHERE user_id = ? ORDER BY ticker", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_position(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
    row = conn.execute(
        f"SELECT {_POSITION_COLS} FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ).fetchone()
    return dict(row) if row else None


def upsert_position(
    conn: sqlite3.Connection, ticker: str, quantity: float, avg_cost: float, user_id: str = DEFAULT_USER_ID
) -> None:
    """Insert or overwrite the position's quantity and avg_cost (values stored as given)."""
    conn.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (_new_id(), user_id, ticker, quantity, avg_cost, now_iso()),
    )


def delete_position(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))


# --- trades -------------------------------------------------------------------------------------


def insert_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float, user_id: str = DEFAULT_USER_ID
) -> dict:
    trade = {
        "id": _new_id(),
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade["id"], user_id, ticker, side, quantity, price, trade["executed_at"]),
    )
    return trade


# --- snapshots ----------------------------------------------------------------------------------


def insert_snapshot(conn: sqlite3.Connection, total_value: float, user_id: str = DEFAULT_USER_ID) -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, round(total_value, 2), now_iso()),
    )


def list_snapshots(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    rows = conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at, rowid",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- chat ---------------------------------------------------------------------------------------


def insert_chat_message(
    conn: sqlite3.Connection, role: str, content: str, actions: list | None, user_id: str = DEFAULT_USER_ID
) -> None:
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (_new_id(), user_id, role, content, None if actions is None else json.dumps(actions), now_iso()),
    )


def recent_chat_messages(conn: sqlite3.Connection, limit: int = 20, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    """The last `limit` messages, oldest first: dicts of role, content, actions (decoded), created_at."""
    rows = conn.execute(
        """
        SELECT role, content, actions, created_at FROM chat_messages
        WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    messages = []
    for r in reversed(rows):
        m = dict(r)
        m["actions"] = None if m["actions"] is None else json.loads(m["actions"])
        messages.append(m)
    return messages


# --- reset --------------------------------------------------------------------------------------


def reset_user(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> None:
    """Clear positions, trades, snapshots and chat; cash back to $10,000; default watchlist."""
    for table in ("positions", "trades", "portfolio_snapshots", "chat_messages", "watchlist"):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    conn.execute(
        """
        INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET cash_balance = excluded.cash_balance
        """,
        (user_id, DEFAULT_CASH, now_iso()),
    )
    _insert_default_watchlist(conn, user_id)
