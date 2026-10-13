"""Chat against the real portfolio service and simulator source (mock LLM, no network)."""

import pytest

from app import database as db
from app.chat import handle_chat
from app.market import PriceCache, SimulatorDataSource
from app.portfolio import get_portfolio


@pytest.fixture
async def real(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    db.init_db(tmp_path / "test.db")
    conn = db.get_connection()
    cache = PriceCache()
    source = SimulatorDataSource(cache)  # never started: prices only change when a test sets them
    await source.sync(db.list_watchlist(conn))
    cache.update("AAPL", 100.0)
    yield conn, cache, source
    db.close_db()


async def test_mock_buy_then_sell_moves_cash(real):
    conn, cache, source = real
    r = await handle_chat(conn, cache, source, "buy 2 AAPL")
    assert r["actions"] == [{"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 2.0, "price": 100.0, "status": "ok"}]
    assert get_portfolio(conn, cache)["cash_balance"] == 9800.0

    r = await handle_chat(conn, cache, source, "sell 5 AAPL")
    assert r["actions"][0]["status"] == "error" and r["actions"][0]["code"] == "INSUFFICIENT_SHARES"
    assert get_portfolio(conn, cache)["cash_balance"] == 9800.0


async def test_mock_watchlist_add_and_remove(real):
    conn, cache, source = real
    r = await handle_chat(conn, cache, source, "add PYPL")
    assert r["actions"] == [{"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"}]
    assert "PYPL" in db.list_watchlist(conn) and cache.get_price("PYPL") is not None

    r = await handle_chat(conn, cache, source, "remove PYPL")
    assert r["actions"][0]["status"] == "ok"
    r = await handle_chat(conn, cache, source, "remove PYPL")
    assert r["actions"][0]["code"] == "NOT_FOUND"


async def test_live_path_builds_prompt_from_real_portfolio(real, monkeypatch):
    conn, cache, source = real
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    sent = []

    def fake_complete(messages):
        sent.append(messages)
        return '{"message": "Buying 1 AAPL.", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}], "watchlist_changes": []}'

    monkeypatch.setattr("app.chat.llm._complete", fake_complete)
    r = await handle_chat(conn, cache, source, "buy an apple share")
    assert r["actions"][0]["status"] == "ok"
    assert "Cash: $10,000.00" in sent[0][1]["content"]
    assert "AAPL: $100.00" in sent[0][1]["content"]
