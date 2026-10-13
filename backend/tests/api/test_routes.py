# backend/tests/api/test_routes.py
import json

import pytest
from fastapi.testclient import TestClient

from app import database as db
from app.main import create_app

DEFAULTS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    monkeypatch.setenv("LLM_MOCK", "true")
    with TestClient(create_app()) as c:
        yield c


def set_price(client, ticker, price):
    client.app.state.cache.update(ticker, price)


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error", "code"} and body["code"] == code and body["error"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_fresh_portfolio(client):
    assert client.get("/api/portfolio").json() == {
        "cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0, "unrealized_pnl": 0.0, "positions": [],
    }


def test_startup_records_snapshot(client):
    snaps = client.get("/api/portfolio/history").json()["snapshots"]
    assert len(snaps) >= 1 and snaps[0]["total_value"] == 10000.0 and snaps[0]["recorded_at"].endswith("Z")


def test_watchlist_defaults_with_prices(client):
    tickers = client.get("/api/watchlist").json()["tickers"]
    assert [t["ticker"] for t in tickers] == DEFAULTS
    assert all(isinstance(t["price"], float) and t["direction"] in ("up", "down", "flat") for t in tickers)


def test_watchlist_add_remove(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 200 and r.json()["ticker"] == "PYPL" and r.json()["price"] is not None
    assert client.post("/api/watchlist", json={"ticker": "PYPL"}).status_code == 200  # idempotent
    assert [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]].count("PYPL") == 1
    r = client.delete("/api/watchlist/pypl")
    assert r.status_code == 204 and r.content == b""
    assert "PYPL" not in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]
    assert_error(client.delete("/api/watchlist/PYPL"), 404, "NOT_FOUND")


def test_watchlist_invalid_ticker(client):
    assert_error(client.post("/api/watchlist", json={"ticker": "123"}), 400, "INVALID_TICKER")
    assert_error(client.post("/api/watchlist", json={}), 400, "INVALID_TICKER")
    assert_error(client.delete("/api/watchlist/BAD-1"), 400, "INVALID_TICKER")


def test_buy_and_sell(client):
    set_price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["trade"]) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
    assert body["trade"]["price"] == 190.0
    assert body["portfolio"]["cash_balance"] == 8100.0
    assert body["portfolio"]["positions"][0]["ticker"] == "AAPL"

    set_price(client, "AAPL", 200.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"})
    assert r.json()["portfolio"]["cash_balance"] == 10100.0
    assert r.json()["portfolio"]["positions"] == []
    assert len(client.get("/api/portfolio/history").json()["snapshots"]) >= 3  # startup + 2 trades


@pytest.mark.parametrize("payload,status,code", [
    ({"ticker": "AAPL", "quantity": 1000, "side": "buy"}, 400, "INSUFFICIENT_CASH"),
    ({"ticker": "AAPL", "quantity": 1, "side": "sell"}, 400, "INSUFFICIENT_SHARES"),
    ({"ticker": "AAPL", "quantity": 0, "side": "buy"}, 400, "INVALID_QUANTITY"),
    ({"ticker": "AAPL", "quantity": 0.00001, "side": "buy"}, 400, "INVALID_QUANTITY"),
    ({"ticker": "AAPL", "quantity": -3, "side": "buy"}, 400, "INVALID_QUANTITY"),
    ({"ticker": "AAPL!", "quantity": 1, "side": "buy"}, 400, "INVALID_TICKER"),
    ({"ticker": "AAPL", "quantity": 1, "side": "short"}, 400, "INVALID_SIDE"),
])
def test_trade_errors(client, payload, status, code):
    set_price(client, "AAPL", 190.0)
    assert_error(client.post("/api/portfolio/trade", json=payload), status, code)


def test_malformed_json_uses_error_shape(client):
    r = client.post("/api/portfolio/trade", content=b"{not json", headers={"content-type": "application/json"})
    assert_error(r, 422, "INVALID_REQUEST")


def test_reset(client):
    client.post("/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"})
    client.delete("/api/watchlist/AAPL")
    r = client.post("/api/reset")
    assert r.status_code == 200
    assert r.json()["cash_balance"] == 10000.0 and r.json()["positions"] == []
    assert [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]] == DEFAULTS
    snaps = client.get("/api/portfolio/history").json()["snapshots"]
    assert [s["total_value"] for s in snaps] == [10000.0]  # exactly one point after reset
    assert client.app.state.source.tickers == frozenset(DEFAULTS)


def test_chat_mock_buy(client):
    pytest.importorskip("app.chat", reason="chat module not landed yet")
    from app import chat
    if not hasattr(chat, "handle_chat"):
        pytest.skip("app.chat.handle_chat not landed yet")
    r = client.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Mock: buying 1 AAPL."
    assert body["actions"][0]["type"] == "trade" and body["actions"][0]["status"] == "ok"
    assert client.get("/api/portfolio").json()["positions"][0]["ticker"] == "AAPL"


def test_chat_empty_message(client):
    assert_error(client.post("/api/chat", json={"message": "  "}), 400, "INVALID_REQUEST")


def test_unknown_api_route_is_404(client):
    assert client.get("/api/nope").status_code == 404


def test_sse_first_event_has_all_priced_tickers(client):
    from app.market import stream

    class OneShot:  # disconnects after the first data frame
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    async def first_frames():
        return [f async for f in stream.price_events(client.app.state.cache, OneShot())]

    frames = client.portal.call(first_frames)
    data = json.loads(next(f for f in frames if f.startswith("data: "))[6:])
    assert set(data) == set(DEFAULTS)
    assert set(data["AAPL"]) == {"ticker", "price", "previous_price", "open_price", "change_percent", "direction", "timestamp"}


def test_db_written_to_env_path(client, tmp_path):
    assert (tmp_path / "api.db").exists()
    assert db.get_cash(client.app.state.conn) == 10000.0


def test_static_mounted_after_api(tmp_path, monkeypatch):
    import app.main as main
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>")
    monkeypatch.setattr(main, "STATIC_DIR", static)
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    with TestClient(main.create_app()) as c:
        assert "FinAlly" in c.get("/").text
        assert c.get("/api/health").json() == {"status": "ok"}


def test_empty_portfolio_numbers_are_floats(client):
    p = client.get("/api/portfolio").json()
    assert all(isinstance(p[k], float) for k in ("cash_balance", "positions_value", "total_value", "unrealized_pnl"))


@pytest.mark.parametrize("payload", [
    {"ticker": "AAPL", "quantity": "lots", "side": "buy"},
    {"side": "buy"},
])
def test_bad_trade_fields_use_error_shape(client, payload):
    r = client.post("/api/portfolio/trade", json=payload)
    assert r.status_code == 400 and set(r.json()) == {"error", "code"}
