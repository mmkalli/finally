import re

import pytest

from app import database as db

ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


# --- transaction --------------------------------------------------------------------------------


def test_transaction_commits(db_path, conn):
    with db.transaction(conn):
        db.set_cash(conn, 500)
    assert not conn.in_transaction
    db.init_db(db_path)  # reopen: data must be on disk
    assert db.get_cash(db.get_connection()) == 500


def test_transaction_rolls_back_all_writes(conn):
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            db.set_cash(conn, 1)
            db.upsert_position(conn, "AAPL", 5, 100)
            db.insert_trade(conn, "AAPL", "buy", 5, 100)
            db.insert_snapshot(conn, 10)
            raise RuntimeError("boom")
    assert not conn.in_transaction
    assert db.get_cash(conn) == 10000.0
    assert db.list_positions(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
    assert db.list_snapshots(conn) == []


def test_nested_transaction_joins_outer(conn):
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            with db.transaction(conn):
                db.set_cash(conn, 1)
            assert conn.in_transaction
            raise RuntimeError
    assert db.get_cash(conn) == 10000.0


# --- cash ---------------------------------------------------------------------------------------


def test_cash_round_trip_rounds_to_cents(conn):
    db.set_cash(conn, 1234.5678)
    assert db.get_cash(conn) == 1234.57


def test_get_cash_unknown_user(conn):
    with pytest.raises(KeyError):
        db.get_cash(conn, user_id="nobody")


# --- watchlist ----------------------------------------------------------------------------------


def test_add_watchlist_appends_and_is_idempotent(conn):
    assert db.add_watchlist(conn, "PYPL") is True
    assert db.add_watchlist(conn, "PYPL") is False
    wl = db.list_watchlist(conn)
    assert wl[-1] == "PYPL" and wl.count("PYPL") == 1 and len(wl) == 11


def test_remove_watchlist(conn):
    assert db.remove_watchlist(conn, "AAPL") is True
    assert db.remove_watchlist(conn, "AAPL") is False
    assert "AAPL" not in db.list_watchlist(conn)


def test_watchlist_is_per_user(conn):
    db.add_watchlist(conn, "PYPL", user_id="other")
    assert db.list_watchlist(conn, user_id="other") == ["PYPL"]
    assert "PYPL" not in db.list_watchlist(conn)


# --- positions ----------------------------------------------------------------------------------


def test_position_lifecycle(conn):
    assert db.get_position(conn, "AAPL") is None
    db.upsert_position(conn, "AAPL", 10, 190.0)
    p = db.get_position(conn, "AAPL")
    assert p["ticker"] == "AAPL" and p["quantity"] == 10 and p["avg_cost"] == 190.0
    assert set(p) == {"ticker", "quantity", "avg_cost", "updated_at"}
    assert ISO_Z.match(p["updated_at"])

    db.upsert_position(conn, "AAPL", 15.5, 191.25)
    p = db.get_position(conn, "AAPL")
    assert p["quantity"] == 15.5 and p["avg_cost"] == 191.25
    assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1

    db.delete_position(conn, "AAPL")
    assert db.get_position(conn, "AAPL") is None
    db.delete_position(conn, "AAPL")  # no-op


def test_list_positions_sorted_plain_dicts(conn):
    db.upsert_position(conn, "TSLA", 1, 250)
    db.upsert_position(conn, "AAPL", 2, 190)
    positions = db.list_positions(conn)
    assert [p["ticker"] for p in positions] == ["AAPL", "TSLA"]
    assert all(type(p) is dict for p in positions)


# --- trades -------------------------------------------------------------------------------------


def test_insert_trade_returns_dict_and_persists(conn):
    t = db.insert_trade(conn, "AAPL", "buy", 10.0, 195.03)
    assert set(t) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
    assert (t["ticker"], t["side"], t["quantity"], t["price"]) == ("AAPL", "buy", 10.0, 195.03)
    assert ISO_Z.match(t["executed_at"])
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (t["id"],)).fetchone()
    assert row["user_id"] == "default" and row["price"] == 195.03 and row["executed_at"] == t["executed_at"]


# --- snapshots ----------------------------------------------------------------------------------


def test_snapshots_ascending(conn):
    for v in (10000, 10050.123, 9990):
        db.insert_snapshot(conn, v)
    snaps = db.list_snapshots(conn)
    assert [s["total_value"] for s in snaps] == [10000, 10050.12, 9990]
    assert set(snaps[0]) == {"total_value", "recorded_at"}
    assert all(ISO_Z.match(s["recorded_at"]) for s in snaps)


# --- chat ---------------------------------------------------------------------------------------


def test_chat_actions_json_round_trip(conn):
    actions = [
        {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 195.03, "status": "ok"},
        {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"},
        {"type": "trade", "ticker": "TSLA", "side": "sell", "quantity": 5.0, "status": "error",
         "error": "Insufficient shares: you hold 0 TSLA", "code": "INSUFFICIENT_SHARES"},
    ]
    db.insert_chat_message(conn, "user", "Buy 10 AAPL", None)
    db.insert_chat_message(conn, "assistant", "Done.", actions)
    db.insert_chat_message(conn, "assistant", "Nothing to do.", [])
    msgs = db.recent_chat_messages(conn)
    assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]
    assert msgs[0]["actions"] is None
    assert msgs[1]["actions"] == actions
    assert msgs[2]["actions"] == []
    assert set(msgs[0]) == {"role", "content", "actions", "created_at"}
    assert ISO_Z.match(msgs[0]["created_at"])


def test_recent_chat_messages_chronological_with_limit(conn):
    for i in range(25):
        db.insert_chat_message(conn, "user" if i % 2 == 0 else "assistant", f"m{i}", None)
    msgs = db.recent_chat_messages(conn)
    assert [m["content"] for m in msgs] == [f"m{i}" for i in range(5, 25)]
    assert [m["content"] for m in db.recent_chat_messages(conn, limit=3)] == ["m22", "m23", "m24"]


# --- reset --------------------------------------------------------------------------------------


def test_reset_user(conn):
    with db.transaction(conn):
        db.set_cash(conn, 42)
        db.add_watchlist(conn, "PYPL")
        db.remove_watchlist(conn, "AAPL")
        db.upsert_position(conn, "PYPL", 3, 60)
        db.insert_trade(conn, "PYPL", "buy", 3, 60)
        db.insert_snapshot(conn, 9999)
        db.insert_chat_message(conn, "user", "hi", None)
        db.insert_chat_message(conn, "assistant", "hello", [], user_id="other")
    with db.transaction(conn):
        db.reset_user(conn)
    assert db.get_cash(conn) == 10000.0
    assert db.list_watchlist(conn) == list(db.DEFAULT_WATCHLIST)
    assert db.list_positions(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
    assert db.list_snapshots(conn) == []
    assert db.recent_chat_messages(conn) == []
    # Other users untouched.
    assert len(db.recent_chat_messages(conn, user_id="other")) == 1
    assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1


def test_reset_user_recreates_missing_profile(conn):
    conn.execute("DELETE FROM users_profile")
    db.reset_user(conn)
    assert db.get_cash(conn) == 10000.0
