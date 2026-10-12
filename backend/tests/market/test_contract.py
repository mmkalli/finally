# backend/tests/market/test_contract.py
"""Shared contract suite: every MarketDataSource must pass (C1-C6)."""
import asyncio
from datetime import datetime

import pytest

from app.market import MassiveDataSource, PriceCache, SimulatorDataSource
from app.market import massive as m
from tests.market.fake_massive import FakeMassive
from tests.market.test_massive import grouped, until


def make_source(kind: str, cache: PriceCache):
    if kind == "simulator":
        return SimulatorDataSource(cache, tick_seconds=0.01)
    fake = FakeMassive(plan="paid" if kind == "massive_snapshot" else "free")
    for i, t in enumerate(["AAPL", "MSFT", "NVDA"]):
        fake.set_quote(t, 100.0 + i, 99.0, 10**9)
    fake.grouped["2026-10-12"] = grouped({"AAPL": 100.0, "MSFT": 101.0, "NVDA": 102.0})
    fake.grouped["2026-10-09"] = grouped({"AAPL": 99.0, "MSFT": 99.0, "NVDA": 99.0})
    return MassiveDataSource(cache, api_key="k", poll_interval=0.01, client=fake.client(),
                             now=lambda: datetime(2026, 10, 12, 18, tzinfo=m.NY))


@pytest.fixture(params=["simulator", "massive_snapshot", "massive_eod"])
async def env(request):
    cache = PriceCache()
    src = make_source(request.param, cache)
    await src.start(["AAPL", "MSFT"])
    await until(lambda: "AAPL" in cache and "MSFT" in cache)       # C1
    yield src, cache
    await src.stop()


async def test_add_is_idempotent_and_prices(env):                 # C2
    src, cache = env
    await src.add_ticker("NVDA")
    await src.add_ticker("NVDA")
    assert "NVDA" in src.tickers and "NVDA" in cache


async def test_remove_drops_from_cache_for_good(env):             # C3, C4
    src, cache = env
    await src.remove_ticker("AAPL")
    await src.remove_ticker("AAPL")
    await asyncio.sleep(0.05)
    assert "AAPL" not in cache and "AAPL" not in src.tickers
    assert set(cache.snapshot()) <= src.tickers


async def test_sync(env):
    src, cache = env
    await src.sync({"MSFT", "NVDA"})
    assert src.tickers == {"MSFT", "NVDA"} and "AAPL" not in cache


async def test_stop_is_idempotent(env):                           # C6
    src, _ = env
    await src.stop()
    await src.stop()
