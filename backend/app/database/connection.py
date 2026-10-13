import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.market.models import format_timestamp

# backend/app/database/connection.py -> parents[3] is the repo root, so the local default is <repo>/db/finally.db.
# In Docker set FINALLY_DB_PATH=/app/db/finally.db (the named volume, PLAN.md §11).
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"
DEFAULT_USER = "default"


def get_db_path() -> Path:
    raw = os.getenv("FINALLY_DB_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_DB_PATH


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the app's single SQLite connection.

    The app shares one connection across the event loop (check_same_thread=False). sqlite3 calls
    never await, so a transaction can't interleave with another coroutine as long as no `await`
    runs between its first write and the commit. Use `with conn:` for a multi-statement
    transaction: it commits on success and rolls back on an exception.
    """
    path = Path(path) if path is not None else get_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def utc_now() -> str:
    """Current time as ISO 8601 UTC with milliseconds, e.g. 2026-10-12T14:03:21.512Z."""
    return format_timestamp(datetime.now(timezone.utc))
