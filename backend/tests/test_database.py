import sqlite3

from app.database import (
    DEFAULT_CASH, DEFAULT_DB_PATH, DEFAULT_WATCHLIST, connect, get_db_path, init_db, reset_to_seed, utc_now,
)

TABLES = {"users_profile", "watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages"}


def watchlist(conn):
    return [r[0] for r in conn.execute("SELECT ticker FROM watchlist ORDER BY added_at, ticker")]


def cash(conn):
    return conn.execute("SELECT cash_balance FROM users_profile WHERE id = 'default'").fetchone()[0]


def test_db_path_defaults_to_repo_db_dir_and_env_overrides(monkeypatch, tmp_path):
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
    assert get_db_path() == DEFAULT_DB_PATH
    assert DEFAULT_DB_PATH.parent.name == "db" and DEFAULT_DB_PATH.parent.parent.joinpath("backend").is_dir()
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "x.db"))
    assert get_db_path() == tmp_path / "x.db"


def test_connect_creates_missing_parent_dir(db_path):
    conn = connect()
    conn.execute("SELECT 1")
    assert db_path.exists()


def test_init_creates_schema_and_seeds(db_path):
    conn = connect()
    init_db(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert TABLES <= names
    assert cash(conn) == DEFAULT_CASH == 10000.0
    assert watchlist(conn) == DEFAULT_WATCHLIST
    assert len(DEFAULT_WATCHLIST) == 10


def test_init_is_idempotent_and_keeps_user_data(db_path):
    conn = connect()
    init_db(conn)
    with conn:
        conn.execute("UPDATE users_profile SET cash_balance = 5.0")
        conn.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
    init_db(conn)
    conn.close()
    conn = connect()
    init_db(conn)
    assert cash(conn) == 5.0
    assert watchlist(conn) == DEFAULT_WATCHLIST[1:]


def test_init_recreates_missing_tables(db_path):
    conn = connect()
    init_db(conn)
    conn.execute("DROP TABLE chat_messages")
    init_db(conn)
    assert conn.execute("SELECT count(*) FROM chat_messages").fetchone()[0] == 0


def test_user_id_defaults_to_default(db_path):
    conn = connect()
    init_db(conn)
    with conn:
        conn.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) VALUES ('p', 'X', 1, 1, ?)",
                     (utc_now(),))
        conn.execute("INSERT INTO trades (id, ticker, side, quantity, price, executed_at) VALUES ('t', 'X', 'buy', 1, 1, ?)",
                     (utc_now(),))
        conn.execute("INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES ('s', 1, ?)", (utc_now(),))
        conn.execute("INSERT INTO chat_messages (id, role, content, created_at) VALUES ('c', 'user', 'hi', ?)",
                     (utc_now(),))
    for table in ("positions", "trades", "portfolio_snapshots", "chat_messages", "watchlist"):
        assert {r[0] for r in conn.execute(f"SELECT user_id FROM {table}")} == {"default"}, table


def test_unique_constraints(db_path):
    conn = connect()
    init_db(conn)
    try:
        conn.execute("INSERT INTO watchlist (id, ticker, added_at) VALUES ('dup', 'AAPL', ?)", (utc_now(),))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("duplicate watchlist ticker accepted")


def test_reset_to_seed(db_path):
    conn = connect()
    init_db(conn)
    with conn:
        conn.execute("UPDATE users_profile SET cash_balance = 1.0")
        conn.execute("DELETE FROM watchlist WHERE ticker IN ('AAPL', 'MSFT')")
        conn.execute("INSERT INTO watchlist (id, ticker, added_at) VALUES ('w', 'PYPL', ?)", (utc_now(),))
        conn.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) VALUES ('p', 'X', 1, 1, ?)",
                     (utc_now(),))
        conn.execute("INSERT INTO trades (id, ticker, side, quantity, price, executed_at) VALUES ('t', 'X', 'buy', 1, 1, ?)",
                     (utc_now(),))
        conn.execute("INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES ('s', 1, ?)", (utc_now(),))
        conn.execute("INSERT INTO chat_messages (id, role, content, created_at) VALUES ('c', 'user', 'hi', ?)",
                     (utc_now(),))
    reset_to_seed(conn)
    assert cash(conn) == 10000.0
    assert watchlist(conn) == DEFAULT_WATCHLIST
    for table in ("positions", "trades", "portfolio_snapshots", "chat_messages"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table


def test_utc_now_format():
    ts = utc_now()
    assert ts.endswith("Z") and "T" in ts and len(ts) == len("2026-10-12T14:03:21.512Z")
