import pytest
from fastapi.testclient import TestClient

from app.database import DEFAULT_WATCHLIST, utc_now
from app.errors import AppError
from app.main import create_app
from app.market import InvalidTickerError, UnknownTickerError
from app.watchlist import add_to_watchlist, remove_from_watchlist

PRICE_FIELDS = {"price", "previous_price", "open_price", "change_percent", "direction", "timestamp"}


def tickers(client) -> list[str]:
    return [entry["ticker"] for entry in client.get("/api/watchlist").json()["tickers"]]


def hold(client, ticker: str, quantity: float = 1.0, avg_cost: float = 100.0) -> None:
    db = client.app.state.db
    with db:
        db.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?)",
                   (f"p-{ticker}", ticker, quantity, avg_cost, utc_now()))


# ---- GET ----

def test_get_returns_default_watchlist_in_order_with_prices(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    entries = r.json()["tickers"]
    assert [e["ticker"] for e in entries] == DEFAULT_WATCHLIST
    for e in entries:
        assert set(e) == PRICE_FIELDS | {"ticker"}
        assert e["price"] > 0
        assert e["direction"] in ("up", "down", "flat")
        assert e["timestamp"].endswith("Z")


def test_get_reports_null_price_fields_for_unpriced_ticker(client):
    client.app.state.price_cache.remove("AAPL")
    aapl = next(e for e in client.get("/api/watchlist").json()["tickers"] if e["ticker"] == "AAPL")
    assert aapl == {"ticker": "AAPL", **{f: None for f in PRICE_FIELDS}}


# ---- POST ----

def test_add_normalizes_prices_and_appends(client):
    r = client.post("/api/watchlist", json={"ticker": "  pypl "})
    assert r.status_code == 200
    entry = r.json()
    assert entry["ticker"] == "PYPL"
    assert set(entry) == PRICE_FIELDS | {"ticker"}
    assert 50 <= entry["price"] <= 300  # unknown-to-simulator ticker gets a random seed price
    assert tickers(client) == DEFAULT_WATCHLIST + ["PYPL"]
    assert "PYPL" in client.app.state.market.tickers


def test_add_is_idempotent(client):
    first = client.post("/api/watchlist", json={"ticker": "PYPL"}).json()
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 200
    assert r.json()["ticker"] == first["ticker"] == "PYPL"
    assert tickers(client).count("PYPL") == 1
    r = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert r.status_code == 200 and r.json()["ticker"] == "AAPL"
    assert tickers(client) == DEFAULT_WATCHLIST + ["PYPL"]


@pytest.mark.parametrize("bad", ["", "   ", "TOOLONGX", "BRK-B", "AB1", "ÄPPL"])
def test_add_rejects_invalid_ticker(client, bad):
    r = client.post("/api/watchlist", json={"ticker": bad})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TICKER"
    assert set(r.json()) == {"error", "code"}
    assert tickers(client) == DEFAULT_WATCHLIST


def test_add_accepts_dotted_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "brk.b"})
    assert r.status_code == 200 and r.json()["ticker"] == "BRK.B"


@pytest.mark.parametrize("body", [{}, {"ticker": 5}, {"symbol": "AAPL"}])
def test_add_rejects_malformed_body(client, body):
    r = client.post("/api/watchlist", json=body)
    assert r.status_code == 400
    assert set(r.json()) == {"error", "code"}
    assert tickers(client) == DEFAULT_WATCHLIST


def test_add_unknown_ticker_writes_nothing(client, monkeypatch):
    market = client.app.state.market

    async def reject(ticker):
        raise UnknownTickerError(f"Unknown ticker: {ticker}")

    monkeypatch.setattr(market, "add_ticker", reject)
    r = client.post("/api/watchlist", json={"ticker": "ZZZZ"})
    assert r.status_code == 400
    assert r.json()["code"] == "UNKNOWN_TICKER"
    assert "ZZZZ" not in tickers(client)
    assert "ZZZZ" not in market.tickers


def test_add_already_watched_does_not_revalidate(client, monkeypatch):
    async def reject(ticker):
        raise UnknownTickerError(ticker)

    monkeypatch.setattr(client.app.state.market, "add_ticker", reject)
    assert client.post("/api/watchlist", json={"ticker": "AAPL"}).status_code == 200


# ---- DELETE ----

def test_remove_unwatched_unheld_ticker_stops_pricing(client):
    r = client.delete("/api/watchlist/nflx")
    assert r.status_code == 204
    assert r.content == b""
    assert "NFLX" not in tickers(client)
    st = client.app.state
    assert "NFLX" not in st.market.tickers
    assert "NFLX" not in st.price_cache


def test_remove_held_ticker_keeps_it_priced(client):
    hold(client, "TSLA")
    assert client.delete("/api/watchlist/TSLA").status_code == 204
    assert "TSLA" not in tickers(client)
    st = client.app.state
    assert "TSLA" in st.market.tickers
    assert "TSLA" in st.price_cache


def test_remove_not_watched_is_404(client):
    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"
    assert set(r.json()) == {"error", "code"}


def test_remove_invalid_ticker_is_400(client):
    r = client.delete("/api/watchlist/AB1")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TICKER"


def test_remove_then_readd(client):
    assert client.delete("/api/watchlist/AAPL").status_code == 204
    assert client.delete("/api/watchlist/AAPL").status_code == 404
    r = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert r.status_code == 200 and r.json()["price"] > 0
    assert tickers(client)[-1] == "AAPL"


def test_watchlist_persists_across_restart(db_path):
    with TestClient(create_app(static_dir=None)) as c:
        c.post("/api/watchlist", json={"ticker": "PYPL"})
        c.delete("/api/watchlist/NFLX")
    with TestClient(create_app(static_dir=None)) as c:
        assert tickers(c) == [t for t in DEFAULT_WATCHLIST if t != "NFLX"] + ["PYPL"]
        assert "PYPL" in c.app.state.market.tickers


# ---- reusable functions (used by chat actions) ----

def test_functions_raise_coded_errors_for_chat(client):
    st = client.app.state

    async def scenario():
        async with st.lock:
            entry = await add_to_watchlist(st.db, st.price_cache, st.market, "ibm")
            assert entry["ticker"] == "IBM" and entry["price"] > 0
            assert await remove_from_watchlist(st.db, st.market, " ibm ") == "IBM"
            with pytest.raises(AppError) as not_found:
                await remove_from_watchlist(st.db, st.market, "IBM")
            assert not_found.value.to_dict()["code"] == "NOT_FOUND"
            with pytest.raises(InvalidTickerError):
                await add_to_watchlist(st.db, st.price_cache, st.market, "123")

    client.portal.call(scenario)
    assert "IBM" not in tickers(client)
    assert "IBM" not in st.market.tickers
