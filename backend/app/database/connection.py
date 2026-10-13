# backend/app/database/connection.py
"""DB path resolution, the shared connection, init and transactions."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .queries import seed_user_if_missing
from .schema import SCHEMA_SQL

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_conn: sqlite3.Connection | None = None


def default_db_path() -> Path:
    """`FINALLY_DB_PATH`, else `<repo>/db/finally.db`.

    Locally the backend lives at `<repo>/backend`, so the DB goes in `<repo>/db`. In Docker the
    backend *is* `/app` (no `backend/` dir), so the DB goes in `/app/db` — the named volume.
    """
    env = os.environ.get("FINALLY_DB_PATH", "").strip()
    if env:
        return Path(env)
    root = _BACKEND_DIR.parent if _BACKEND_DIR.name == "backend" else _BACKEND_DIR
    return root / "db" / "finally.db"


def _open(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: no implicit transactions; `transaction()` issues BEGIN explicitly.
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path: str | Path | None = None) -> None:
    """Open the shared connection, create any missing tables and seed if empty. Idempotent.

    Calling it again (e.g. with a new tmp path in tests) closes the previous connection.
    """
    global _conn
    close_db()
    conn = _open(path if path is not None else default_db_path())
    conn.executescript(SCHEMA_SQL)
    with transaction(conn):
        seed_user_if_missing(conn)
    _conn = conn


def get_connection() -> sqlite3.Connection:
    """The shared connection; initializes the default DB on first use."""
    if _conn is None:
        init_db()
    assert _conn is not None
    return _conn


def close_db() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """`BEGIN IMMEDIATE` … COMMIT, or ROLLBACK on any exception.

    Nested use joins the outer transaction (the outermost block commits or rolls back).
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
