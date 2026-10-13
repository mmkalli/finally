# Testing Patterns

**Analysis Date:** 2026-10-13

## Test Framework

**Runner:**
- pytest >=8 with pytest-asyncio >=0.24 (dev dependency group in `backend/pyproject.toml`)
- Config: `[tool.pytest.ini_options]` in `backend/pyproject.toml`: `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `testpaths = ["tests"]`, `pythonpath = ["."]`

**Assertion Library:** plain `assert` (pytest).

**Run Commands:**
```bash
cd backend && uv run pytest              # Run all tests
cd backend && uv run pytest tests/market/test_massive.py -k snapshot   # Subset
cd backend && uv run pytest -x -q        # Fail fast
# Coverage: not configured (pytest-cov not installed)
```

Note: `backend/pyproject.toml` currently contains unresolved merge-conflict markers; fix before running.

## Test File Organization

**Location:** separate `backend/tests/` tree mirroring `backend/app/` (`tests/market/` for `app/market/`), with `__init__.py` files so `from tests.market.fake_massive import ...` works.

**Naming:** `test_<topic>.py`; shared fakes in non-test-named modules (`fake_massive.py`).

```
backend/tests/
└── market/
    ├── fake_massive.py            # httpx.MockTransport fake of Massive REST API
    ├── test_cache_and_tickers.py  # PriceCache + normalize_ticker
    ├── test_contract.py           # shared suite run against every MarketDataSource
    ├── test_massive.py            # pure helpers, snapshot mode, EOD mode
    ├── test_simulator.py          # GBM math, seed prices, determinism, correlation
    └── test_stream.py             # SSE frame generation
```

Planned (per PLAN.md §12, not yet present): portfolio/trade tests, LLM parsing + mock mode, API route tests, frontend logic tests, Playwright E2E in `test/`.

## Test Structure

**Suite Organization:** flat module-level functions (no test classes); sections separated by `# ---- name ----` comments. Compact tuple assertions:

```python
def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    u = cache.update("AAPL", 190.123)
    assert (u.price, u.previous_price, u.open_price) == (190.12, 190.12, 190.12)
```

**Patterns:**
- Async tests are plain `async def test_...` (auto mode; no decorator needed).
- Async fixtures use `@pytest.fixture` with `yield` and stop the source in teardown (`await src.stop()`).
- Parametrized contract suite: `@pytest.fixture(params=["simulator", "massive_snapshot", "massive_eod"])` in `tests/market/test_contract.py`; any new `MarketDataSource` must be added to `make_source` there.
- Polling helper instead of fixed sleeps: `await until(lambda: "AAPL" in cache)` (defined in `tests/market/test_massive.py`, reused by contract tests; default 2s timeout).
- Use small intervals (`tick_seconds=0.01`, `poll_interval=0.02`) to keep tests fast.
- Randomness is seeded: `GBMSimulator(rng=random.Random(7))`; statistical tests use `statistics.correlation`.

## Mocking

**Framework:** no mock library; hand-written fakes + `monkeypatch`.

**Patterns:**
```python
# HTTP: FakeMassive in tests/market/fake_massive.py
fake = FakeMassive(plan="paid")            # "free" -> snapshot endpoint returns 403
fake.set_quote("AAPL", 190.12, 188.50, 1 * NS)
src = MassiveDataSource(cache, api_key="k", poll_interval=0.02, client=fake.client())

# Clock injection
MassiveDataSource(..., now=lambda: datetime(2026, 10, 12, 18, tzinfo=m.NY))

# Patch module internals (tests/market/test_stream.py)
monkeypatch.setattr(s.asyncio, "sleep", fake_sleep)
monkeypatch.setattr(s.time, "monotonic", lambda: clock[0])
```
- `FakeMassive` records `calls` and supports `status_override` for error-path tests; the client is an `httpx.AsyncClient(transport=httpx.MockTransport(...))`.
- `FakeRequest` in `tests/market/test_stream.py` stubs `is_disconnected()` to bound SSE generator loops.

**What to Mock:** network (httpx), wall clock, `asyncio.sleep` in stream loops, RNG (seed it).
**What NOT to Mock:** `PriceCache`, `GBMSimulator`, and `SimulatorDataSource` are used for real.

## Fixtures and Factories

- Inline builders: `grouped({"AAPL": 100.0})` builds Massive grouped-daily results; `run(sim, tickers, n)` in `test_simulator.py` simulates paths.
- Dates in tests use fixed 2026-10 dates (Mon `2026-10-12`, Fri `2026-10-09`) for deterministic trading-day logic.
- No conftest.py; fixtures live in the test module that uses them.

## Coverage

**Requirements:** none enforced. Market-data package is well covered; everything outside `app/market/` (DB, portfolio, API routes, LLM, factory, demo, priced.py) has no tests yet.

## Test Types

**Unit Tests:** pure logic (cache, ticker validation, GBM, `pick_price`, date helpers) and async sources against fakes.
**Integration Tests:** contract suite across all sources; SSE frame generator tests. No real network or DB.
**E2E Tests:** Not yet present (`test/` with Playwright + `docker-compose.test.yml` is planned; use `LLM_MOCK=true` and `POST /api/reset` per PLAN.md §12).

## Common Patterns

**Async waiting:**
```python
await src.start(["AAPL", "MSFT"])
await until(lambda: "AAPL" in cache and "MSFT" in cache)
```

**Parametrized pure tests:**
```python
@pytest.mark.parametrize("now,expected", [(datetime(...), date(...)), ...])
def test_latest_published_day(now, expected): ...
```

**Error testing:** use `pytest.raises(InvalidTickerError)` / `UnknownTickerError` (imported from `app.market`).

---

*Testing analysis: 2026-10-13*
