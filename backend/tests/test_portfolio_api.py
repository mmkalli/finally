import pytest

from app.database import DEFAULT_WATCHLIST, utc_now

PORTFOLIO_KEYS = {"cash_balance", "positions_value", "total_value", "unrealized_pnl", "positions"}
POSITION_KEYS = {"ticker", "quantity", "avg_cost", "current_price", "market_value", "unrealized_pnl", "pnl_percent"}


def buy(client, ticker, quantity, side="buy"):
    return client.post("/api/portfolio/trade", json={"ticker": ticker, "quantity": quantity, "side": side})


def test_fresh_portfolio(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json() == {"cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0,
                        "unrealized_pnl": 0.0, "positions": []}


def test_buy_returns_trade_and_updated_portfolio(client):
    price = client.app.state.price_cache.get_price("AAPL")
    r = buy(client, "aapl", 10)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"trade", "portfolio"}
    assert set(body["trade"]) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
    assert body["trade"]["ticker"] == "AAPL" and body["trade"]["quantity"] == 10.0
    fill = body["trade"]["price"]
    assert fill == pytest.approx(price, rel=0.1)  # the simulator may have ticked since
    p = body["portfolio"]
    assert set(p) == PORTFOLIO_KEYS
    assert p["cash_balance"] == round(10000 - 10 * fill, 2)
    assert [pos["ticker"] for pos in p["positions"]] == ["AAPL"]
    assert set(p["positions"][0]) == POSITION_KEYS
    assert client.get("/api/portfolio").json()["positions"][0]["avg_cost"] == fill


def test_sell_closes_position(client):
    buy(client, "MSFT", 3)
    r = buy(client, "MSFT", 3, side="sell")
    assert r.status_code == 200
    assert r.json()["trade"]["side"] == "sell"
    assert r.json()["portfolio"]["positions"] == []


def test_trade_records_snapshot_for_history(client):
    before = client.get("/api/portfolio/history").json()["snapshots"]
    buy(client, "AAPL", 1)
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    snaps = r.json()["snapshots"]
    assert len(snaps) == len(before) + 1
    assert set(snaps[-1]) == {"total_value", "recorded_at"}


@pytest.mark.parametrize(("payload", "code"), [
    ({"ticker": "AAPL", "quantity": 1_000_000, "side": "buy"}, "INSUFFICIENT_CASH"),
    ({"ticker": "AAPL", "quantity": 1, "side": "sell"}, "INSUFFICIENT_SHARES"),
    ({"ticker": "AAPL", "quantity": 0, "side": "buy"}, "INVALID_QUANTITY"),
    ({"ticker": "AAPL", "quantity": 0.00001, "side": "buy"}, "INVALID_QUANTITY"),
    ({"ticker": "AAPL", "quantity": -5, "side": "sell"}, "INVALID_QUANTITY"),
    ({"ticker": "AAPL1", "quantity": 1, "side": "buy"}, "INVALID_TICKER"),
    ({"ticker": "AAPL", "quantity": 1, "side": "short"}, "INVALID_REQUEST"),
    ({"ticker": "AAPL", "side": "buy"}, "INVALID_REQUEST"),
])
def test_trade_errors(client, payload, code):
    r = client.post("/api/portfolio/trade", json=payload)
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == code and isinstance(body["error"], str) and set(body) == {"error", "code"}
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_buying_unwatched_ticker(client):
    st = client.app.state
    r = buy(client, "pypl", 1)
    assert r.status_code == 200 and r.json()["trade"]["ticker"] == "PYPL"
    assert "PYPL" in st.market.tickers  # priced because held
    assert st.db.execute("SELECT 1 FROM watchlist WHERE ticker = 'PYPL'").fetchone() is None
    buy(client, "PYPL", 1, side="sell")
    assert "PYPL" not in st.market.tickers and "PYPL" not in st.price_cache


def test_reset(client):
    st = client.app.state
    buy(client, "ORCL", 1)
    with st.db:
        st.db.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
        st.db.execute("INSERT INTO chat_messages (id, role, content, created_at) VALUES ('m', 'user', 'hi', ?)",
                      (utc_now(),))

    r = client.post("/api/reset")
    assert r.status_code == 200
    assert r.json() == {"cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0,
                        "unrealized_pnl": 0.0, "positions": []}
    assert [row[0] for row in st.db.execute("SELECT ticker FROM watchlist ORDER BY added_at")] == DEFAULT_WATCHLIST
    assert st.db.execute("SELECT count(*) FROM trades").fetchone()[0] == 0
    assert st.db.execute("SELECT count(*) FROM chat_messages").fetchone()[0] == 0
    assert st.market.tickers == frozenset(DEFAULT_WATCHLIST)
    snaps = client.get("/api/portfolio/history").json()["snapshots"]
    assert [s["total_value"] for s in snaps] == [10000.0]
