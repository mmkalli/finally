import asyncio
import math

import pytest

from app.database import DEFAULT_WATCHLIST, connect, init_db, utc_now
from app.errors import AppError
from app.market import MarketDataSource, PriceCache, UnknownTickerError
from app.portfolio import execute_trade, get_history, get_portfolio, reset_portfolio


class FakeMarket(MarketDataSource):
    """Prices tickers from a fixed table, so fills are deterministic. Tickers missing from it stay unpriced."""

    def __init__(self, cache: PriceCache, prices: dict[str, float], unknown: frozenset[str] = frozenset()):
        super().__init__(cache)
        self.prices = prices
        self.unknown = unknown
        self._tickers: set[str] = set()

    async def start(self, tickers):
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self):
        pass

    async def add_ticker(self, ticker):
        if ticker in self.unknown:
            raise UnknownTickerError(f"Unknown ticker: {ticker}")
        self._tickers.add(ticker)
        if ticker in self.prices and ticker not in self._cache:
            self._cache.update(ticker, self.prices[ticker])

    async def remove_ticker(self, ticker):
        self._tickers.discard(ticker)
        self._cache.remove(ticker)

    @property
    def tickers(self):
        return frozenset(self._tickers)

    def set_price(self, ticker, price):
        self.prices[ticker] = price
        if ticker in self._tickers:
            self._cache.update(ticker, price)


@pytest.fixture
def env(db_path):
    conn = connect()
    init_db(conn)
    cache = PriceCache()
    market = FakeMarket(cache, {"AAPL": 190.0, "MSFT": 400.0, "TSLA": 250.0, "ORCL": 120.0})
    asyncio.run(market.start(DEFAULT_WATCHLIST))
    yield conn, cache, market
    conn.close()


def trade(env, ticker, side, quantity):
    conn, cache, market = env
    return asyncio.run(execute_trade(conn, cache, market, ticker, side, quantity))


def rejected(env, ticker, side, quantity) -> AppError:
    with pytest.raises(AppError) as exc:
        trade(env, ticker, side, quantity)
    return exc.value


def cash(conn):
    return conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0]


def position(conn, ticker):
    row = conn.execute("SELECT quantity, avg_cost FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    return tuple(row) if row else None


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# ---- buys and sells ----

def test_buy_debits_cash_opens_position_logs_trade_and_snapshot(env):
    conn = env[0]
    t = trade(env, "aapl ", "buy", 10)
    assert {k: t[k] for k in ("ticker", "side", "quantity", "price")} == \
        {"ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 190.0}
    assert t["id"] and t["executed_at"].endswith("Z")
    assert cash(conn) == 8100.0
    assert position(conn, "AAPL") == (10.0, 190.0)
    row = conn.execute("SELECT id, ticker, side, quantity, price, executed_at FROM trades").fetchone()
    assert tuple(row) == (t["id"], "AAPL", "buy", 10.0, 190.0, t["executed_at"])
    assert [s["total_value"] for s in get_history(conn)] == [10000.0]


def test_second_buy_uses_weighted_average_cost(env):
    conn, _, market = env
    trade(env, "AAPL", "buy", 10)
    market.set_price("AAPL", 200.0)
    trade(env, "AAPL", "buy", 30)
    qty, avg = position(conn, "AAPL")
    assert qty == 40.0 and avg == pytest.approx((10 * 190 + 30 * 200) / 40)  # 197.5
    assert cash(conn) == 10000 - 1900 - 6000


def test_partial_sell_keeps_avg_cost_and_credits_cash(env):
    conn, _, market = env
    trade(env, "AAPL", "buy", 10)
    market.set_price("AAPL", 210.0)
    t = trade(env, "AAPL", "sell", 4)
    assert t["side"] == "sell" and t["price"] == 210.0
    assert position(conn, "AAPL") == (6.0, 190.0)
    assert cash(conn) == 8100.0 + 840.0


def test_sell_at_a_loss(env):
    conn, cache, market = env
    trade(env, "TSLA", "buy", 4)  # 1000.00
    market.set_price("TSLA", 200.0)
    trade(env, "TSLA", "sell", 2)
    assert cash(conn) == 9400.0
    p = get_portfolio(conn, cache)["positions"][0]
    assert p["unrealized_pnl"] == -100.0 and p["pnl_percent"] == -20.0


def test_selling_whole_position_deletes_row(env):
    conn = env[0]
    trade(env, "AAPL", "buy", 2.5)
    trade(env, "AAPL", "sell", 2.5)
    assert position(conn, "AAPL") is None
    assert cash(conn) == 10000.0
    assert count(conn, "trades") == 2


def test_selling_fractional_remainder_after_rounding_deletes_row(env):
    conn = env[0]
    trade(env, "AAPL", "buy", 1.23456)  # stored as 1.2346
    assert position(conn, "AAPL")[0] == 1.2346
    trade(env, "AAPL", "sell", 1.23459)  # rounds to 1.2346 -> sells everything
    assert position(conn, "AAPL") is None


def test_buy_spending_exactly_all_cash(env):
    conn = env[0]
    trade(env, "MSFT", "buy", 25)  # 25 * 400 = 10000
    assert cash(conn) == 0.0 and math.copysign(1, cash(conn)) == 1  # not -0.0


# ---- rounding ----

def test_quantity_rounded_to_4dp_and_cash_to_2dp(env):
    conn, _, market = env
    market.set_price("AAPL", 190.37)
    t = trade(env, "AAPL", "buy", 0.123456)
    assert t["quantity"] == 0.1235
    assert cash(conn) == round(10000 - round(0.1235 * 190.37, 2), 2) == 9976.49


# ---- rejections: nothing is written ----

def assert_untouched(conn):
    assert cash(conn) == 10000.0
    assert count(conn, "positions") == count(conn, "trades") == count(conn, "portfolio_snapshots") == 0


def test_insufficient_cash(env):
    e = rejected(env, "MSFT", "buy", 30)
    assert e.code == "INSUFFICIENT_CASH" and e.status == 400
    assert e.message == "Insufficient cash: need $12,000.00, have $10,000.00"
    assert_untouched(env[0])


def test_selling_more_than_held(env):
    conn = env[0]
    trade(env, "AAPL", "buy", 2)
    e = rejected(env, "AAPL", "sell", 2.5)
    assert e.code == "INSUFFICIENT_SHARES" and e.message == "Insufficient shares: you hold 2 AAPL"
    assert position(conn, "AAPL") == (2.0, 190.0) and count(conn, "trades") == 1


def test_selling_without_a_position(env):
    e = rejected(env, "TSLA", "sell", 5)
    assert (e.code, e.message) == ("INSUFFICIENT_SHARES", "Insufficient shares: you hold 0 TSLA")
    assert_untouched(env[0])


@pytest.mark.parametrize("quantity", [0, -1, 0.00004, -0.00004, float("nan"), float("inf"), True, "10", None])
def test_invalid_quantity(env, quantity):
    assert rejected(env, "AAPL", "buy", quantity).code == "INVALID_QUANTITY"
    assert_untouched(env[0])


@pytest.mark.parametrize("ticker", ["", "AAPL1", "TOOLONGX", "BRK-B", None])
def test_invalid_ticker(env, ticker):
    assert rejected(env, ticker, "buy", 1).code == "INVALID_TICKER"


@pytest.mark.parametrize("side", ["hold", "", None])
def test_invalid_side(env, side):
    assert rejected(env, "AAPL", side, 1).code == "INVALID_REQUEST"


def test_side_is_case_insensitive(env):
    assert trade(env, "AAPL", " BUY", 1)["side"] == "buy"


def test_no_cached_price(env):
    conn, _, market = env
    e = rejected(env, "ZZZ", "buy", 1)  # FakeMarket accepts ZZZ but never prices it
    assert (e.code, e.message) == ("NO_PRICE", "No price yet for ZZZ")
    assert_untouched(conn)
    assert "ZZZ" not in market.tickers  # re-synced: neither watched nor held


def test_unknown_ticker_from_source(env):
    conn, cache, _ = env
    env = (conn, cache, FakeMarket(cache, {}, unknown=frozenset({"NOPE"})))
    assert rejected(env, "NOPE", "buy", 1).code == "UNKNOWN_TICKER"


# ---- priced-ticker set ----

def test_buying_unwatched_ticker_prices_it_until_sold(env):
    conn, cache, market = env
    trade(env, "ORCL", "buy", 1)
    assert "ORCL" in market.tickers and cache.get_price("ORCL") == 120.0
    assert conn.execute("SELECT 1 FROM watchlist WHERE ticker = 'ORCL'").fetchone() is None
    trade(env, "ORCL", "sell", 1)
    assert "ORCL" not in market.tickers and "ORCL" not in cache


def test_failed_buy_of_unwatched_ticker_leaves_it_unpriced(env):
    _, cache, market = env
    rejected(env, "ORCL", "buy", 1000)
    assert "ORCL" not in market.tickers and "ORCL" not in cache


def test_watched_ticker_stays_priced_after_selling_out(env):
    _, _, market = env
    trade(env, "AAPL", "buy", 1)
    trade(env, "AAPL", "sell", 1)
    assert "AAPL" in market.tickers


# ---- concurrency ----

def test_lock_serializes_concurrent_buys(env):
    conn, cache, market = env
    lock = asyncio.Lock()

    async def locked_buy():
        async with lock:
            return await execute_trade(conn, cache, market, "MSFT", "buy", 15)  # $6,000 each

    async def both():
        return await asyncio.gather(locked_buy(), locked_buy(), return_exceptions=True)

    results = asyncio.run(both())
    assert sum(isinstance(r, dict) for r in results) == 1
    assert [r.code for r in results if isinstance(r, AppError)] == ["INSUFFICIENT_CASH"]
    assert cash(conn) == 4000.0


# ---- valuation ----

def test_portfolio_valuation(env):
    conn, cache, market = env
    trade(env, "AAPL", "buy", 10)  # 1900
    with conn:
        conn.execute("INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) "
                     "VALUES ('p', 'ZZZ', 2, 50.123, ?)", (utc_now(),))
    market.set_price("AAPL", 195.03)
    p = get_portfolio(conn, cache)
    assert p["positions"] == [
        {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 190.0, "current_price": 195.03,
         "market_value": 1950.3, "unrealized_pnl": 50.3, "pnl_percent": 2.65},
        # unpriced -> valued at avg_cost
        {"ticker": "ZZZ", "quantity": 2.0, "avg_cost": 50.12, "current_price": 50.12,
         "market_value": 100.25, "unrealized_pnl": 0.0, "pnl_percent": 0.0},
    ]
    assert p["cash_balance"] == 8100.0
    assert p["positions_value"] == 2050.55
    assert p["total_value"] == round(p["cash_balance"] + p["positions_value"], 2) == 10150.55
    assert p["unrealized_pnl"] == 50.3


def test_empty_portfolio(env):
    conn, cache, _ = env
    assert get_portfolio(conn, cache) == {
        "cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0, "unrealized_pnl": 0.0,
        "positions": [],
    }


def test_history_is_oldest_first(env):
    conn = env[0]
    with conn:
        conn.executemany("INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES (?, ?, ?)",
                         [("b", 10100.456, "2026-10-13T10:00:30.000Z"), ("a", 10000, "2026-10-13T10:00:00.000Z")])
    assert get_history(conn) == [
        {"total_value": 10000.0, "recorded_at": "2026-10-13T10:00:00.000Z"},
        {"total_value": 10100.46, "recorded_at": "2026-10-13T10:00:30.000Z"},
    ]


# ---- reset ----

def test_reset_restores_seed_state_and_priced_set(env):
    conn, cache, market = env
    trade(env, "ORCL", "buy", 1)
    with conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
        conn.execute("INSERT INTO chat_messages (id, role, content, created_at) VALUES ('m', 'user', 'hi', ?)",
                     (utc_now(),))
    asyncio.run(reset_portfolio(conn, cache, market))
    assert get_portfolio(conn, cache)["positions"] == [] and cash(conn) == 10000.0
    assert count(conn, "trades") == count(conn, "chat_messages") == 0
    assert [s["total_value"] for s in get_history(conn)] == [10000.0]
    assert market.tickers == frozenset(DEFAULT_WATCHLIST)
