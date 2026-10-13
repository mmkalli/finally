# backend/app/database/__init__.py
"""SQLite persistence: schema, seed, init, shared connection and data-access functions."""

from .connection import close_db, default_db_path, get_connection, init_db, transaction
from .queries import (
    add_watchlist,
    delete_position,
    get_cash,
    get_position,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    list_positions,
    list_snapshots,
    list_watchlist,
    now_iso,
    recent_chat_messages,
    remove_watchlist,
    reset_user,
    seed_user_if_missing,
    set_cash,
    upsert_position,
)
from .seed import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST

__all__ = [
    "DEFAULT_CASH",
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "add_watchlist",
    "close_db",
    "default_db_path",
    "delete_position",
    "get_cash",
    "get_connection",
    "get_position",
    "init_db",
    "insert_chat_message",
    "insert_snapshot",
    "insert_trade",
    "list_positions",
    "list_snapshots",
    "list_watchlist",
    "now_iso",
    "recent_chat_messages",
    "remove_watchlist",
    "reset_user",
    "seed_user_if_missing",
    "set_cash",
    "upsert_position",
]
