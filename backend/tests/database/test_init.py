import re
import sqlite3
from pathlib import Path

import pytest

from app import database as db
from app.database import connection
from app.database.schema import TABLES
from app.market.priced import load_priced_tickers

ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_init_creates_parent_dir_and_all_tables(db_path, conn):
    assert db_path.exists()
    assert set(TABLES) <= _tables(conn)


def test_connection_settings(conn):
    assert conn.row_factory is sqlite3.Row
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_seed_contents(conn):
    assert db.get_cash(conn) == 10000.0
    assert db.list_watchlist(conn) == ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
    assert db.list_positions(conn) == []
    assert db.list_snapshots(conn) == []
    assert db.recent_chat_messages(conn) == []
    created = conn.execute("SELECT created_at FROM users_profile WHERE id='default'").fetchone()[0]
    assert ISO_Z.match(created)


def test_init_is_idempotent_and_preserves_data(db_path, conn):
    with db.transaction(conn):
        db.set_cash(conn, 1234.5)
        db.remove_watchlist(conn, "AAPL")
        db.upsert_position(conn, "TSLA", 2, 200.0)
    db.init_db(db_path)
    conn2 = db.get_connection()
    assert conn2 is not conn
    assert db.get_cash(conn2) == 1234.5
    assert "AAPL" not in db.list_watchlist(conn2)
    assert len(db.list_watchlist(conn2)) == 9
    assert db.get_position(conn2, "TSLA")["quantity"] == 2
    assert conn2.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1


def test_empty_watchlist_not_reseeded_on_restart(db_path, conn):
    with db.transaction(conn):
        for t in db.list_watchlist(conn):
            db.remove_watchlist(conn, t)
    db.init_db(db_path)
    assert db.list_watchlist(db.get_connection()) == []


def test_init_creates_missing_tables(db_path, conn):
    conn.execute("DROP TABLE chat_messages")
    db.init_db(db_path)
    assert "chat_messages" in _tables(db.get_connection())


def test_init_memory():
    db.init_db(":memory:")
    try:
        assert db.get_cash(db.get_connection()) == 10000.0
    finally:
        db.close_db()


def test_get_connection_returns_shared_instance(conn):
    assert db.get_connection() is conn


def test_user_id_defaults(conn):
    conn.execute("INSERT INTO trades (id, ticker, side, quantity, price, executed_at) VALUES ('x','A','buy',1,1,'t')")
    assert conn.execute("SELECT user_id FROM trades WHERE id='x'").fetchone()[0] == "default"
    conn.execute("DELETE FROM users_profile")
    conn.execute("INSERT INTO users_profile (created_at) VALUES ('t')")
    assert tuple(conn.execute("SELECT id, cash_balance FROM users_profile").fetchone()) == ("default", 10000.0)


def test_unique_constraints(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES ('w', 'default', 'AAPL', 't')"
        )
    db.upsert_position(conn, "AAPL", 1, 1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES ('p', 'default', 'AAPL', 1, 1, 't')"
        )
    # Same ticker for a different user is fine.
    conn.execute("INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES ('w2', 'other', 'AAPL', 't')")


def test_check_constraints(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_trade(conn, "AAPL", "hold", 1, 1)
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_chat_message(conn, "system", "x", None)


def test_priced_tickers_query_still_works(conn):
    db.upsert_position(conn, "PYPL", 1, 60)
    db.remove_watchlist(conn, "NFLX")
    priced = load_priced_tickers(conn)
    assert "PYPL" in priced and "NFLX" not in priced and len(priced) == 10


def test_default_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "x.db"))
    assert db.default_db_path() == tmp_path / "x.db"


def test_default_path_local_repo(monkeypatch):
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
    repo = Path(__file__).resolve().parents[3]
    assert db.default_db_path() == repo / "db" / "finally.db"


def test_default_path_docker_layout(monkeypatch):
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
    monkeypatch.setattr(connection, "_BACKEND_DIR", Path("/app"))
    assert db.default_db_path() == Path("/app/db/finally.db")


def test_get_connection_lazily_inits_default(monkeypatch, tmp_path):
    db.close_db()
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "lazy" / "f.db"))
    try:
        assert db.get_cash(db.get_connection()) == 10000.0
        assert (tmp_path / "lazy" / "f.db").exists()
    finally:
        db.close_db()
