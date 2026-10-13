# backend/tests/market/test_simulator.py
import asyncio
import math
import random
import statistics

from app.market import GBMSimulator, PriceCache, SimulatorDataSource


def corr(a, b):
    return statistics.correlation(a, b)


def log_returns(path):
    return [math.log(b / a) for a, b in zip(path, path[1:])]


def run(sim, tickers, n):
    for t in tickers:
        sim.add(t)
    paths = {t: [sim.price(t)] for t in tickers}
    for _ in range(n):
        for t, p in sim.step().items():
            paths[t].append(p)
    return paths


def test_seed_prices():
    sim = GBMSimulator(rng=random.Random(1))
    assert sim.add("AAPL") == 190.00
    assert 50 <= sim.add("PYPL") <= 300
    assert sim.add("PYPL") == sim.price("PYPL")  # idempotent, no reseed


def test_deterministic():
    a = run(GBMSimulator(rng=random.Random(7)), ["AAPL", "PYPL"], 100)
    b = run(GBMSimulator(rng=random.Random(7)), ["AAPL", "PYPL"], 100)
    assert a == b


def test_prices_stay_positive_under_extreme_vol():
    sim = GBMSimulator(rng=random.Random(3), time_scale=10_000)
    paths = run(sim, ["TSLA"], 20_000)
    assert min(paths["TSLA"]) > 0


def test_gbm_moments():
    sim = GBMSimulator(rng=random.Random(5), event_probability=0)
    r = log_returns(run(sim, ["AAPL"], 50_000)["AAPL"])
    dt = sim._dt
    sigma = 0.25
    assert abs(statistics.stdev(r) - sigma * math.sqrt(dt)) < 0.02 * sigma * math.sqrt(dt)
    assert abs(statistics.fmean(r) - (0.08 - sigma**2 / 2) * dt) < 3 * sigma * math.sqrt(dt / 50_000)


def test_correlation_structure():
    sim = GBMSimulator(rng=random.Random(42), event_probability=0)
    paths = run(sim, ["AAPL", "MSFT", "JPM", "V", "TSLA"], 30_000)
    r = {t: log_returns(p) for t, p in paths.items()}
    assert abs(corr(r["AAPL"], r["MSFT"]) - 0.61) < 0.03   # same sector (tech)
    assert abs(corr(r["JPM"], r["V"]) - 0.50) < 0.03       # same sector (finance)
    assert abs(corr(r["AAPL"], r["JPM"]) - 0.25) < 0.03    # cross sector
    assert abs(corr(r["AAPL"], r["TSLA"]) - 0.25) < 0.03   # TSLA: market only


def test_events_move_2_to_5_percent():
    sim = GBMSimulator(rng=random.Random(9), event_probability=1.0, time_scale=1e-9)
    sim.add("AAPL")
    for _ in range(200):
        before = sim.price("AAPL")
        after = sim.step()["AAPL"]
        assert 0.0199 <= abs(after / before - 1) <= 0.0501


def test_no_events_small_moves():
    sim = GBMSimulator(rng=random.Random(9), event_probability=0)
    paths = run(sim, ["AAPL"], 10_000)["AAPL"]
    assert max(abs(b / a - 1) for a, b in zip(paths, paths[1:])) < 0.01


def test_remove():
    sim = GBMSimulator(rng=random.Random(1))
    sim.add("AAPL"); sim.add("MSFT"); sim.remove("AAPL")
    assert set(sim.step()) == {"MSFT"}


async def test_adapter_lifecycle():
    cache = PriceCache()
    src = SimulatorDataSource(cache, tick_seconds=0.01)
    await src.start(["AAPL", "MSFT"])
    assert cache.get_price("AAPL") == 190.00                 # seeded synchronously
    await src.add_ticker("PYPL")
    assert "PYPL" in cache                                   # priced before add returns
    first_ts = cache.get("AAPL").timestamp
    await asyncio.sleep(0.05)
    assert cache.get("AAPL").timestamp > first_ts            # ticking
    assert cache.get("AAPL").open_price == 190.00            # open = seed
    await src.remove_ticker("MSFT")
    await asyncio.sleep(0.03)
    assert "MSFT" not in cache and "MSFT" not in src.tickers
    await src.stop(); await src.stop()
