import pytest

from app.database import close_db, get_connection, init_db
from app.errors import AppError
from app.market.cache import PriceCache
from app.market.tickers import normalize_ticker
import app.chat.service as chat_service


@pytest.fixture
def conn(tmp_path):
    init_db(tmp_path / "test.db")
    yield get_connection()
    close_db()


@pytest.fixture
def cache():
    c = PriceCache()
    c.update("AAPL", 190.0)
    c.update("MSFT", 410.0)
    return c


@pytest.fixture
def env(monkeypatch):
    """Clean LLM env: not mock, no key. Tests opt in to what they need."""
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return monkeypatch


class FakePortfolio:
    """Stand-in for app.portfolio.service so chat tests don't depend on trade math.

    Buys succeed while cash lasts; sells need a held position; tickers are validated like the real thing.
    """

    def __init__(self, cache):
        self.cache = cache
        self.cash = 10000.0
        self.held: dict[str, float] = {}
        self.watch = {"AAPL", "MSFT"}
        self.calls: list[tuple] = []

    async def execute_trade(self, conn, cache, source, ticker, side, quantity):
        ticker = normalize_ticker(ticker)
        self.calls.append(("trade", ticker, side, quantity))
        if side == "sell" and quantity > self.held.get(ticker, 0):
            raise AppError("INSUFFICIENT_SHARES", f"Insufficient shares: you hold 0 {ticker}")
        price = cache.get_price(ticker)
        if price is None:
            raise AppError("NO_PRICE", f"No price yet for {ticker}")
        if side == "buy":
            if quantity * price > self.cash:
                raise AppError("INSUFFICIENT_CASH", f"Insufficient cash for {ticker}")
            self.cash -= quantity * price
            self.held[ticker] = self.held.get(ticker, 0) + quantity
        else:
            self.held[ticker] -= quantity
        return {"id": "t1", "ticker": ticker, "side": side, "quantity": round(quantity, 4),
                "price": price, "executed_at": "2026-10-13T00:00:00.000Z"}

    def get_portfolio(self, conn, cache):
        positions = [
            {"ticker": t, "quantity": q, "avg_cost": 100.0, "current_price": cache.get_price(t),
             "market_value": q * cache.get_price(t), "unrealized_pnl": 1.0, "pnl_percent": 1.0}
            for t, q in self.held.items() if q
        ]
        pv = sum(p["market_value"] for p in positions)
        return {"cash_balance": self.cash, "positions_value": pv, "total_value": self.cash + pv,
                "unrealized_pnl": 0.0, "positions": positions}

    async def add_to_watchlist(self, conn, cache, source, ticker):
        ticker = normalize_ticker(ticker)
        self.calls.append(("add", ticker))
        self.watch.add(ticker)
        return {"ticker": ticker}

    async def remove_from_watchlist(self, conn, cache, source, ticker):
        ticker = normalize_ticker(ticker)
        self.calls.append(("remove", ticker))
        if ticker not in self.watch:
            raise AppError("NOT_FOUND", f"{ticker} is not on the watchlist", 404)
        self.watch.discard(ticker)


@pytest.fixture
def portfolio(cache, monkeypatch):
    fake = FakePortfolio(cache)
    for name in ("execute_trade", "get_portfolio", "add_to_watchlist", "remove_from_watchlist"):
        monkeypatch.setattr(chat_service, name, getattr(fake, name))
    return fake


@pytest.fixture
def llm_reply(env, monkeypatch):
    """Configure a live (non-mock) setup whose LLM returns the given raw text. Records the prompts sent."""
    env.setenv("OPENROUTER_API_KEY", "test-key")
    sent: list[list[dict]] = []

    def set_reply(raw):
        def fake_complete(messages):
            sent.append(messages)
            if isinstance(raw, Exception):
                raise raw
            return raw

        monkeypatch.setattr(chat_service.llm, "_complete", fake_complete)
        return sent

    return set_reply
