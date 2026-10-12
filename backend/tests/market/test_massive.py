# backend/tests/market/test_massive.py
import asyncio
from datetime import date, datetime

import pytest

from app.market import MassiveDataSource, PriceCache, UnknownTickerError
from app.market import massive as m
from tests.market.fake_massive import FakeMassive

NS = 1_000_000_000
MON_EVENING = datetime(2026, 10, 12, 18, 0, tzinfo=m.NY)   # Monday after close


def grouped(prices: dict[str, float], t_ms: int = 1_760_300_000_000) -> list[dict]:
    return [{"T": k, "c": v, "o": v, "h": v, "l": v, "v": 1, "t": t_ms} for k, v in prices.items()]


async def until(cond, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "condition not met in time"
        await asyncio.sleep(0.005)


# ---- pure helpers --------------------------------------------------------------------------

def test_pick_price_order_and_zero_skipping():
    item = {"lastTrade": {"p": 0}, "min": {"c": 0}, "day": {"c": 101.5}, "prevDay": {"c": 100}}
    assert m.pick_price(item, allow_prev_close=False) == 101.5
    item = {"lastTrade": {"p": 102.0}, "min": {"c": 101}, "day": {"c": 100}}
    assert m.pick_price(item, allow_prev_close=False) == 102.0
    reset_window = {"min": {"c": 0}, "day": {"c": 0}, "prevDay": {"c": 100}}
    assert m.pick_price(reset_window, allow_prev_close=False) is None
    assert m.pick_price(reset_window, allow_prev_close=True) == 100


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 10, 12, 18, 0, tzinfo=m.NY), date(2026, 10, 12)),   # Mon after close -> Mon
    (datetime(2026, 10, 12, 10, 0, tzinfo=m.NY), date(2026, 10, 9)),    # Mon morning -> Fri
    (datetime(2026, 10, 11, 12, 0, tzinfo=m.NY), date(2026, 10, 9)),    # Sun -> Fri
])
def test_latest_published_day(now, expected):
    assert m.latest_published_day(now) == expected


# ---- snapshot mode --------------------------------------------------------------------------

@pytest.fixture
async def paid():
    fake = FakeMassive(plan="paid")
    fake.set_quote("AAPL", 190.12, 188.50, 1 * NS)
    fake.set_quote("MSFT", 420.00, 415.00, 1 * NS)
    fake.set_quote("PYPL", 70.00, 69.00, 1 * NS)
    cache = PriceCache()
    src = MassiveDataSource(cache, api_key="k", poll_interval=0.02, client=fake.client())
    await src.start(["AAPL", "MSFT"])
    await until(lambda: "AAPL" in cache and "MSFT" in cache)
    yield fake, cache, src
    await src.stop()


async def test_snapshot_prices_and_open(paid):
    fake, cache, src = paid
    u = cache.get("AAPL")
    assert (u.price, u.open_price, u.change_percent) == (190.12, 188.50, 0.86)
    assert src.name == "massive:snapshot"


async def test_snapshot_change_detection(paid):
    fake, cache, src = paid
    v = cache.version
    await asyncio.sleep(0.1)                      # several polls, nothing changed
    assert cache.version == v
    fake.set_quote("AAPL", 191.00, 188.50, 2 * NS)
    await until(lambda: cache.get_price("AAPL") == 191.00)
    assert cache.get("AAPL").previous_price == 190.12


async def test_snapshot_add_validates(paid):
    fake, cache, src = paid
    await src.add_ticker("PYPL")
    assert cache.get_price("PYPL") == 70.00       # priced before add returns
    with pytest.raises(UnknownTickerError):
        await src.add_ticker("ZZZZ")
    assert "ZZZZ" not in src.tickers


async def test_snapshot_remove_is_final(paid):
    fake, cache, src = paid
    await src.remove_ticker("MSFT")
    fake.set_quote("MSFT", 999.0, 415.0, 5 * NS)
    await asyncio.sleep(0.1)
    assert "MSFT" not in cache


async def test_reset_window_does_not_jump_to_prev_close(paid):
    fake, cache, src = paid
    fake.snapshot["AAPL"] = {"ticker": "AAPL", "updated": 9 * NS,
                             "day": {"c": 0}, "min": {"c": 0}, "prevDay": {"c": 190.12}}
    await asyncio.sleep(0.1)
    assert cache.get_price("AAPL") == 190.12 and cache.get("AAPL").timestamp == m.ns_to_datetime(1 * NS)


async def test_401_stops_poller_and_adds_unvalidated():
    fake = FakeMassive(plan="paid")
    fake.status_override = 401
    cache = PriceCache()
    src = MassiveDataSource(cache, api_key="bad", poll_interval=0.02, client=fake.client())
    await src.start(["AAPL"])
    await until(lambda: src._task.done())
    await src.add_ticker("PYPL")                  # returns immediately, no 10 s wait
    assert "PYPL" in src.tickers and "PYPL" not in cache
    await src.stop()


async def test_429_backs_off(monkeypatch):
    fake = FakeMassive(plan="paid")
    fake.status_override = 429
    delays = []
    real_sleep = asyncio.sleep

    async def fake_sleep(d):
        delays.append(d)
        await real_sleep(0)

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    src = MassiveDataSource(PriceCache(), api_key="k", poll_interval=2, client=fake.client())
    await src.start(["AAPL"])
    await until(lambda: len(delays) >= 3)
    assert 60.0 in delays
    await src.stop()


# ---- eod mode (free plan) -------------------------------------------------------------------

@pytest.fixture
async def free():
    fake = FakeMassive(plan="free")
    fake.grouped["2026-10-12"] = grouped({"AAPL": 190.0, "MSFT": 420.0, "PYPL": 70.0})
    fake.grouped["2026-10-09"] = grouped({"AAPL": 188.0, "MSFT": 425.0, "PYPL": 70.0})
    cache = PriceCache()
    src = MassiveDataSource(cache, api_key="k", client=fake.client(), now=lambda: MON_EVENING)
    await src.start(["AAPL", "MSFT"])
    await until(lambda: "AAPL" in cache and "MSFT" in cache)
    yield fake, cache, src
    await src.stop()


async def test_eod_detects_and_prices(free):
    fake, cache, src = free
    assert src.name == "massive:eod"
    u = cache.get("AAPL")
    assert (u.price, u.open_price, u.change_percent) == (190.0, 188.0, 1.06)
    # 1 detect + Monday + (weekend skipped) Friday = 3 calls
    assert len(fake.calls) == 3


async def test_eod_add_validates_without_calls(free):
    fake, cache, src = free
    n = len(fake.calls)
    await src.add_ticker("PYPL")
    assert cache.get_price("PYPL") == 70.0
    with pytest.raises(UnknownTickerError):
        await src.add_ticker("ZZZZ")
    assert len(fake.calls) == n


async def test_throttle_never_allows_sixth_call_in_a_minute(monkeypatch):
    clock = [1000.0]
    slept = []

    async def fake_sleep(d):
        slept.append(d)
        clock[0] += d

    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    src = MassiveDataSource(PriceCache(), api_key="k", client=FakeMassive().client())
    for _ in range(5):
        await src._throttle()
    assert slept == []
    await src._throttle()
    assert slept and clock[0] >= 1060.0
    await src.stop()
