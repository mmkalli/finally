import json
import sqlite3

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.database import DEFAULT_WATCHLIST, connect, init_db, utc_now
from app.errors import AppError
from app.main import create_app
from app.market import InvalidTickerError, sync_priced_tickers
from app.market.stream import stream_prices


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_lifespan_wires_state_and_prices_default_watchlist(client, db_path):
    st = client.app.state
    assert isinstance(st.db, sqlite3.Connection)
    assert st.market.tickers == frozenset(DEFAULT_WATCHLIST)
    assert all(t in st.price_cache for t in DEFAULT_WATCHLIST)  # simulator primes the cache on start
    assert db_path.exists()
    assert st.db.execute("SELECT count(*) FROM portfolio_snapshots").fetchone()[0] >= 1  # recorded at startup


def test_startup_prices_held_tickers_that_are_not_watched(db_path):
    conn = connect()
    init_db(conn)
    with conn:
        conn.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) VALUES ('p', 'PYPL', 1, 70, ?)",
                     (utc_now(),))
        conn.execute("DELETE FROM watchlist WHERE ticker = 'NFLX'")
    conn.close()
    with TestClient(create_app(static_dir=None)) as c:
        assert c.app.state.market.tickers == (frozenset(DEFAULT_WATCHLIST) - {"NFLX"}) | {"PYPL"}


def test_shutdown_closes_db(db_path):
    with TestClient(create_app(static_dir=None)) as c:
        db = c.app.state.db
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_sync_priced_tickers_follows_watchlist_and_positions(client):
    st = client.app.state

    async def scenario():
        async with st.lock:
            with st.db:
                st.db.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) "
                              "VALUES ('p', 'ORCL', 1, 100, ?)", (utc_now(),))
                st.db.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
            await sync_priced_tickers(st.db, st.market)

    client.portal.call(scenario)
    assert "ORCL" in st.market.tickers and "ORCL" in st.price_cache
    assert "AAPL" not in st.market.tickers


# ---- errors ----

class Body(BaseModel):
    quantity: float


@pytest.fixture
def error_client(db_path):
    app = create_app(static_dir=None)
    router = APIRouter()

    @router.get("/api/_test/app-error")
    async def app_error():
        raise AppError("INSUFFICIENT_CASH", "Insufficient cash: need $1,950.30, have $1,200.00")

    @router.get("/api/_test/not-found")
    async def not_found():
        raise AppError("NOT_FOUND", "PYPL is not on the watchlist")

    @router.get("/api/_test/market-error")
    async def market_error():
        raise InvalidTickerError("Invalid ticker: 'AB1'")

    @router.post("/api/_test/body")
    async def body(b: Body):
        return {}

    app.include_router(router)
    with TestClient(app) as c:
        yield c


def test_app_error_shape(error_client):
    r = error_client.get("/api/_test/app-error")
    assert r.status_code == 400
    assert r.json() == {"error": "Insufficient cash: need $1,950.30, have $1,200.00", "code": "INSUFFICIENT_CASH"}
    r = error_client.get("/api/_test/not-found")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_market_error_shape(error_client):
    r = error_client.get("/api/_test/market-error")
    assert r.status_code == 400
    assert r.json() == {"error": "Invalid ticker: 'AB1'", "code": "INVALID_TICKER"}


def test_validation_error_shape(error_client):
    r = error_client.post("/api/_test/body", json={"quantity": "lots"})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_REQUEST"
    assert set(r.json()) == {"error", "code"}


def test_unknown_route_shape(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": "Not Found", "code": "NOT_FOUND"}


def test_app_error_to_dict():
    err = AppError("NO_PRICE", "No price yet for PYPL")
    assert err.status == 400
    assert err.to_dict() == {"error": "No price yet for PYPL", "code": "NO_PRICE"}


# ---- static files ----

def test_static_mount_serves_index_without_shadowing_api(db_path, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>")
    with TestClient(create_app(static_dir=static)) as c:
        assert "FinAlly" in c.get("/").text
        assert c.get("/api/health").json() == {"status": "ok"}


def test_no_static_dir_means_no_mount(db_path, tmp_path):
    with TestClient(create_app(static_dir=tmp_path / "missing")) as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/health").status_code == 200


# ---- SSE ----

class FakeRequest:
    """Enough of a Request for the stream route; disconnects after `frames` loop iterations."""

    def __init__(self, app, frames: int):
        self.app = app
        self.left = frames

    async def is_disconnected(self):
        self.left -= 1
        return self.left < 0


def test_stream_route_registered(client):
    assert client.app.url_path_for("stream_prices") == "/api/stream/prices"


def test_stream_first_frame_has_every_priced_ticker(client):
    async def first_frames():
        response = await stream_prices(FakeRequest(client.app, frames=1))
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        return [f async for f in response.body_iterator]

    frames = client.portal.call(first_frames)
    data = [json.loads(f[6:]) for f in frames if f.startswith("data: ")]
    assert frames[0] == "retry: 1000\n\n"
    assert set(data[0]) == set(DEFAULT_WATCHLIST)
    aapl = data[0]["AAPL"]
    assert set(aapl) == {"ticker", "price", "previous_price", "open_price", "change_percent", "direction", "timestamp"}
