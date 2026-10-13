# backend/tests/portfolio/test_service.py
import pytest

from app import database as db
from app.errors import AppError
from app.market import PriceCache, SimulatorDataSource
from app.portfolio import (
    add_to_watchlist,
    execute_trade,
    get_portfolio,
    list_watchlist_entries,
    remove_from_watchlist,
    reset_portfolio,
)


@pytest.fixture
async def env(tmp_path):
    db.init_db(tmp_path / "test.db")
    conn = db.get_connection()
    cache = PriceCache()
    source = SimulatorDataSource(cache)  # never started: prices only change when a test sets them
    await source.sync(db.list_watchlist(conn))
    cache.update("AAPL", 100.0)
    cache.update("MSFT", 200.0)
    yield conn, cache, source
    db.close_db()


async def trade(env, ticker, side, qty):
    return await execute_trade(*env, ticker, side, qty)


async def expect_error(code, coro):
    with pytest.raises(AppError) as e:
        await coro
    assert e.value.code == code
    return e.value


# --- buys / sells -------------------------------------------------------------------------------


async def test_buy_updates_cash_position_trade_and_snapshot(env):
    conn, cache, _ = env
    t = await trade(env, "aapl", "buy", 10)
    assert t["ticker"] == "AAPL" and t["side"] == "buy" and t["quantity"] == 10 and t["price"] == 100.0
    p = get_portfolio(conn, cache)
    assert p["cash_balance"] == 9000.0
    assert p["positions"] == [{
        "ticker": "AAPL", "quantity": 10.0, "avg_cost": 100.0, "current_price": 100.0,
        "market_value": 1000.0, "unrealized_pnl": 0.0, "pnl_percent": 0.0,
    }]
    assert p["total_value"] == 10000.0
    assert [s["total_value"] for s in db.list_snapshots(conn)] == [10000.0]


async def test_weighted_average_cost(env):
    conn, cache, _ = env
    await trade(env, "AAPL", "buy", 10)
    cache.update("AAPL", 130.0)
    await trade(env, "AAPL", "buy", 5)
    pos = db.get_position(conn, "AAPL")
    assert pos["quantity"] == 15
    assert pos["avg_cost"] == pytest.approx(110.0)  # (10*100 + 5*130) / 15


async def test_pnl_and_portfolio_totals(env):
    conn, cache, _ = env
    await trade(env, "AAPL", "buy", 10)
    cache.update("AAPL", 105.5)
    p = get_portfolio(conn, cache)
    pos = p["positions"][0]
    assert pos["current_price"] == 105.5
    assert pos["market_value"] == 1055.0
    assert pos["unrealized_pnl"] == 55.0
    assert pos["pnl_percent"] == 5.5
    assert p["positions_value"] == 1055.0
    assert p["unrealized_pnl"] == 55.0
    assert p["total_value"] == 10055.0


async def test_sell_at_loss_keeps_avg_cost(env):
    conn, cache, _ = env
    await trade(env, "AAPL", "buy", 10)
    cache.update("AAPL", 90.0)
    await trade(env, "AAPL", "sell", 4)
    pos = db.get_position(conn, "AAPL")
    assert pos["quantity"] == 6 and pos["avg_cost"] == 100.0
    assert db.get_cash(conn) == 9000.0 + 360.0


async def test_selling_whole_position_deletes_row(env):
    conn, cache, _ = env
    await trade(env, "AAPL", "buy", 2.5)
    await trade(env, "AAPL", "sell", 2.5)
    assert db.get_position(conn, "AAPL") is None
    assert get_portfolio(conn, cache)["positions"] == []
    assert db.get_cash(conn) == 10000.0


async def test_fractional_quantity_rounded_to_4dp(env):
    conn, _, _ = env
    t = await trade(env, "AAPL", "buy", 1.123456)
    assert t["quantity"] == 1.1235
    assert db.get_position(conn, "AAPL")["quantity"] == 1.1235
    assert db.get_cash(conn) == round(10000 - 112.35, 2)


async def test_cash_rounded_to_2dp(env):
    conn, cache, _ = env
    cache.update("AAPL", 33.33)
    await trade(env, "AAPL", "buy", 0.3333)
    assert db.get_cash(conn) == round(10000 - 0.3333 * 33.33, 2)


# --- validation ---------------------------------------------------------------------------------


async def test_insufficient_cash(env):
    conn, _, _ = env
    e = await expect_error("INSUFFICIENT_CASH", trade(env, "AAPL", "buy", 101))
    assert e.message == "Insufficient cash: need $10,100.00, have $10,000.00"
    assert db.get_cash(conn) == 10000.0 and db.list_positions(conn) == []
    assert db.list_snapshots(conn) == []  # rolled back


async def test_buy_exactly_all_cash(env):
    conn, _, _ = env
    await trade(env, "AAPL", "buy", 100)
    assert db.get_cash(conn) == 0.0


async def test_insufficient_shares(env):
    e = await expect_error("INSUFFICIENT_SHARES", trade(env, "TSLA", "sell", 5))
    assert e.message == "Insufficient shares: you hold 0 TSLA"
    await trade(env, "AAPL", "buy", 1)
    await expect_error("INSUFFICIENT_SHARES", trade(env, "AAPL", "sell", 1.5))


@pytest.mark.parametrize("qty", [0, -1, 0.00004, "abc", None, float("nan")])
async def test_invalid_quantity(env, qty):
    await expect_error("INVALID_QUANTITY", trade(env, "AAPL", "buy", qty))


@pytest.mark.parametrize("ticker", ["", "AAPL1", "TOOLONGX", None, "A-B"])
async def test_invalid_ticker(env, ticker):
    await expect_error("INVALID_TICKER", trade(env, ticker, "buy", 1))


async def test_invalid_side(env):
    await expect_error("INVALID_SIDE", trade(env, "AAPL", "hold", 1))


async def test_no_price(env):
    conn, cache, source = env

    async def add_without_price(ticker):  # e.g. Massive before its first poll
        source._sim.add(ticker)

    source.add_ticker = add_without_price
    await expect_error("NO_PRICE", trade(env, "PYPL", "buy", 1))
    assert "PYPL" not in source.tickers  # dropped again: neither watched nor held


# --- priced set ---------------------------------------------------------------------------------


async def test_buying_unwatched_ticker_prices_it_but_does_not_watch(env):
    conn, cache, source = env
    await trade(env, "PYPL", "buy", 1)
    assert "PYPL" in source.tickers and cache.get_price("PYPL") is not None
    assert "PYPL" not in db.list_watchlist(conn)
    await trade(env, "PYPL", "sell", 1)
    assert "PYPL" not in source.tickers and "PYPL" not in cache


async def test_removing_held_ticker_from_watchlist_keeps_it_priced(env):
    conn, cache, source = env
    await trade(env, "AAPL", "buy", 1)
    await remove_from_watchlist(conn, cache, source, "AAPL")
    assert "AAPL" not in db.list_watchlist(conn)
    assert "AAPL" in source.tickers
    await remove_from_watchlist(conn, cache, source, "MSFT")
    assert "MSFT" not in source.tickers and "MSFT" not in cache


# --- watchlist ----------------------------------------------------------------------------------


async def test_add_watchlist_returns_entry_and_is_idempotent(env):
    conn, cache, source = env
    entry = await add_to_watchlist(conn, cache, source, " pypl ")
    assert entry["ticker"] == "PYPL" and 50 <= entry["price"] <= 300
    assert set(entry) == {"ticker", "price", "previous_price", "open_price", "change_percent", "direction", "timestamp"}
    again = await add_to_watchlist(conn, cache, source, "PYPL")
    assert again["ticker"] == "PYPL"
    assert db.list_watchlist(conn).count("PYPL") == 1
    assert [e["ticker"] for e in list_watchlist_entries(conn, cache)][-1] == "PYPL"


async def test_add_watchlist_invalid(env):
    await expect_error("INVALID_TICKER", add_to_watchlist(*env, "12"))


async def test_add_watchlist_unknown_ticker_writes_nothing(env):
    from app.market import UnknownTickerError
    conn, cache, source = env

    async def reject(ticker):
        raise UnknownTickerError(f"Unknown ticker: {ticker}")

    source.add_ticker = reject
    await expect_error("UNKNOWN_TICKER", add_to_watchlist(conn, cache, source, "ZZZZ"))
    assert "ZZZZ" not in db.list_watchlist(conn)


async def test_remove_watchlist_not_found(env):
    e = await expect_error("NOT_FOUND", remove_from_watchlist(*env, "PYPL"))
    assert e.status == 404


async def test_watchlist_entry_without_price_has_null_fields(env):
    conn, cache, _ = env
    cache.remove("AAPL")
    entry = next(e for e in list_watchlist_entries(conn, cache) if e["ticker"] == "AAPL")
    assert entry["price"] is None and entry["direction"] is None


async def test_unpriced_position_falls_back_to_avg_cost(env):
    conn, cache, _ = env
    await trade(env, "AAPL", "buy", 2)
    cache.remove("AAPL")
    pos = get_portfolio(conn, cache)["positions"][0]
    assert pos["current_price"] == 100.0 and pos["unrealized_pnl"] == 0.0


# --- reset --------------------------------------------------------------------------------------


async def test_reset(env):
    conn, cache, source = env
    await trade(env, "PYPL", "buy", 1)
    await remove_from_watchlist(conn, cache, source, "AAPL")
    db.insert_chat_message(conn, "user", "hi", None)
    p = await reset_portfolio(conn, cache, source)
    assert p["cash_balance"] == 10000.0 and p["positions"] == []
    assert db.list_watchlist(conn) == list(db.DEFAULT_WATCHLIST)
    assert [s["total_value"] for s in db.list_snapshots(conn)] == [10000.0]  # one fresh starting point
    assert db.recent_chat_messages(conn) == []
    assert source.tickers == frozenset(db.DEFAULT_WATCHLIST)
