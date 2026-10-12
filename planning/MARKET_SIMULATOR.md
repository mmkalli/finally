# Market Simulator — Approach and Code Structure

The default price source for FinAlly when `MASSIVE_API_KEY` is not set. It implements the `MarketDataSource` interface from `MARKET_INTERFACE.md` and writes into the shared `PriceCache`. Requirements come from `PLAN.md` §6:

- Geometric Brownian motion (GBM), with drift and volatility per ticker
- Updates about every 500 ms
- Correlated moves (tech moves with tech)
- Occasional sudden 2–5 % "events"
- Realistic seed prices; any valid unknown ticker gets a random $50–$300 seed
- In-process background task, no external dependencies

The code below was run and its statistics checked (§7). It uses only the Python standard library (`math`, `random`, `asyncio`). With 10–30 tickers, a plain loop is far cheaper than a 500 ms tick, so numpy isn't needed.

---

## 1. Code structure

```
backend/app/market/
├── seed_data.py    # TickerProfile, PROFILES, sector loadings, defaults, profile_for()
├── simulator.py    # GBMSimulator (pure, synchronous, deterministic with a seeded RNG)
│                   # SimulatorDataSource (async adapter: MarketDataSource ↔ GBMSimulator ↔ PriceCache)
```

The split is deliberate:

| Piece | Knows about | Doesn't know about |
|---|---|---|
| `seed_data` | Tickers, prices, sectors | Time, randomness, asyncio |
| `GBMSimulator` | Maths, randomness | asyncio, the cache, wall-clock time |
| `SimulatorDataSource` | asyncio, `PriceCache`, the interface | Maths |

`GBMSimulator` is a plain object with `add / remove / step()`. Tests drive it with `random.Random(seed)` and call `step()` in a loop, with no event loop or sleeping, and get exactly reproducible paths.

---

## 2. The maths

### 2.1 GBM step

For each ticker with annual drift μ and annual volatility σ, one tick is the exact GBM solution over a time step Δt:

```
S(t+Δt) = S(t) · exp( (μ − σ²/2)·Δt  +  σ·√Δt·Z )      Z ~ N(0,1), correlated across tickers (§2.3)
```

- It's multiplicative, so prices **can never go to zero or below**.
- The `−σ²/2` term keeps the expected price growing at μ (Itô correction).
- The simulator keeps **full-precision** prices internally. Only the cache rounds to 2 dp. Rounding inside the simulator would bias small moves and could freeze a price.

### 2.2 Time step and time compression

Δt is measured in **trading years**: 252 days × 6.5 h = 5,896,800 trading seconds.

At real speed, a 500 ms tick is Δt ≈ 8.5 × 10⁻⁸. For AAPL (σ = 25 %) that's about 1.4 ¢ per tick and ~0.6 % per hour, which looks almost flat on a terminal screen. So the simulator **compresses time**:

```
Δt = tick_seconds × time_scale / 5,896,800        (default time_scale = 10)
```

At `time_scale = 10`, one real second covers ten seconds of market time. Measured over 28,800 ticks, i.e. 4 hours of real time (§7):

| Ticker (σ) | Typical move per tick | per minute | per hour |
|---|---|---|---|
| V (18 %) | 0.017 % | 0.18 % | 1.4 % |
| AAPL (25 %) | 0.023 % (~4 ¢) | 0.25 % | 2.0 % |
| TSLA (55 %) | 0.051 % | 0.55 % | 4.3 % |

That's visible on every tick and lively enough for a demo, while still looking like a stock. `time_scale` is a constructor argument, so it's easy to tune.

Drift barely matters at these timescales. μ = 8 %/yr is about 0.003 % per real hour. It's kept for correctness and so long-running servers trend a little upward rather than purely random-walking.

### 2.3 Correlation: a factor model

Each tick draws one **market** shock M, one shock S_k per **sector** k, and one **idiosyncratic** shock εᵢ per ticker, all independent N(0,1). Ticker i in sector k gets:

```
Zᵢ = β_m·M  +  β_k·S_k  +  √(1 − β_m² − β_k²)·εᵢ
```

That gives Var(Zᵢ) = 1, and:

```
corr(i, j) = β_m² + β_k²     same sector
corr(i, j) = β_m²            different sectors / no sector
```

| Loading | Value | Resulting correlation |
|---|---|---|
| Market β_m | 0.5 | 0.25 between any two tickers |
| Tech β_k | 0.6 | 0.61 within tech (AAPL, GOOGL, MSFT, NVDA, META) |
| Finance β_k | 0.5 | 0.50 within finance (JPM, V) |
| Consumer β_k | 0.4 | 0.41 within consumer (AMZN, NFLX) |
| Auto / unknown | 0.0 | TSLA and new tickers only follow the market (0.25) |

Why a factor model rather than a correlation matrix plus Cholesky decomposition:

- **It's always valid.** Any loadings with β_m² + β_k² ≤ 1 give a positive-semidefinite correlation. A hand-written matrix can easily fail to be, and then Cholesky throws.
- **Adding or removing tickers is free.** There's no matrix to rebuild or re-factor when the watchlist changes.
- **It's O(n) per tick** and easy to explain: "everything moves with the market, and tech also moves with tech."

### 2.4 Events

On each tick, each ticker independently has a probability `p = 0.0005` of an event. An event multiplies the price by `1 ± U(2 %, 5 %)` (sign 50/50) on top of the normal GBM move.

- Per ticker: one event every 2,000 ticks ≈ **every 17 minutes**.
- Across the 10 default tickers: **≈ 36 events per hour**, about one every 100 s, so something dramatic is usually on screen within a couple of minutes. (Measured: 35 in one simulated hour.)

The jump is permanent; there's no mean reversion, like a real news-driven gap. Because of the events, realised volatility comes out a bit above σ. That's intended.

---

## 3. Seed data — `seed_data.py`

```python
# backend/app/market/seed_data.py
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TickerProfile:
    seed_price: float
    drift: float        # annualized μ
    volatility: float   # annualized σ
    sector: str | None  # tickers in the same sector share a sector factor


MARKET_LOADING = 0.5
SECTOR_LOADINGS: dict[str, float] = {
    "tech": 0.6,
    "finance": 0.5,
    "consumer": 0.4,
    "auto": 0.0,
}

# Seed prices are illustrative "realistic" levels (PLAN.md §6: AAPL ~$190, GOOGL ~$175); tune freely.
PROFILES: dict[str, TickerProfile] = {
    "AAPL":  TickerProfile(190.00, 0.08, 0.25, "tech"),
    "GOOGL": TickerProfile(175.00, 0.08, 0.28, "tech"),
    "MSFT":  TickerProfile(420.00, 0.08, 0.24, "tech"),
    "AMZN":  TickerProfile(185.00, 0.09, 0.30, "consumer"),
    "TSLA":  TickerProfile(250.00, 0.05, 0.55, "auto"),
    "NVDA":  TickerProfile(130.00, 0.12, 0.45, "tech"),
    "META":  TickerProfile(500.00, 0.09, 0.35, "tech"),
    "JPM":   TickerProfile(200.00, 0.06, 0.20, "finance"),
    "V":     TickerProfile(280.00, 0.07, 0.18, "finance"),
    "NFLX":  TickerProfile(650.00, 0.08, 0.38, "consumer"),
}

DEFAULT_DRIFT = 0.05
DEFAULT_VOLATILITY = 0.30
UNKNOWN_PRICE_RANGE = (50.0, 300.0)


def profile_for(ticker: str, rng: random.Random) -> TickerProfile:
    """Known ticker → its profile. Unknown (but format-valid) ticker → random seed, default μ/σ, no sector."""
    known = PROFILES.get(ticker)
    if known:
        return known
    return TickerProfile(
        seed_price=round(rng.uniform(*UNKNOWN_PRICE_RANGE), 2),
        drift=DEFAULT_DRIFT,
        volatility=DEFAULT_VOLATILITY,
        sector=None,
    )
```

You can add more well-known tickers to `PROFILES` (e.g. `AMD`, `INTC` → tech; `BAC`, `GS` → finance) to make watchlist additions feel realistic. Anything not listed still works.

---

## 4. `GBMSimulator` — pure engine

```python
# backend/app/market/simulator.py  (part 1)
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .seed_data import MARKET_LOADING, SECTOR_LOADINGS, TickerProfile, profile_for

TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600


@dataclass(slots=True)
class _State:
    price: float            # full precision; rounding happens in PriceCache
    profile: TickerProfile


class GBMSimulator:
    """Correlated GBM with random jump events. Synchronous and deterministic for a seeded rng."""

    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        tick_seconds: float = 0.5,
        time_scale: float = 10.0,
        event_probability: float = 0.0005,
        event_range: tuple[float, float] = (0.02, 0.05),
    ) -> None:
        self._rng = rng or random.Random()
        self._dt = tick_seconds * time_scale / TRADING_SECONDS_PER_YEAR
        self._event_probability = event_probability
        self._event_range = event_range
        self._states: dict[str, _State] = {}

    # ---- ticker set ----

    def add(self, ticker: str) -> float:
        """Start simulating `ticker` (idempotent). Returns its current price."""
        state = self._states.get(ticker)
        if state is None:
            profile = profile_for(ticker, self._rng)
            state = self._states[ticker] = _State(profile.seed_price, profile)
        return state.price

    def remove(self, ticker: str) -> None:
        self._states.pop(ticker, None)

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._states)

    def price(self, ticker: str) -> float | None:
        state = self._states.get(ticker)
        return state.price if state else None

    # ---- one tick ----

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick. Returns {ticker: new_price}."""
        gauss = self._rng.gauss
        market = gauss(0.0, 1.0)
        sectors: dict[str, float] = {}       # sector shocks, drawn lazily once per tick
        sqrt_dt = math.sqrt(self._dt)
        out: dict[str, float] = {}
        for ticker, state in self._states.items():
            p = state.profile
            z = self._correlated_shock(p.sector, market, sectors)
            log_return = (p.drift - 0.5 * p.volatility**2) * self._dt + p.volatility * sqrt_dt * z
            price = state.price * math.exp(log_return)
            if self._rng.random() < self._event_probability:
                move = self._rng.uniform(*self._event_range)
                price *= 1 + move if self._rng.random() < 0.5 else 1 - move
            state.price = price
            out[ticker] = price
        return out

    def _correlated_shock(self, sector: str | None, market: float, sectors: dict[str, float]) -> float:
        b_m = MARKET_LOADING
        b_s = SECTOR_LOADINGS.get(sector, 0.0) if sector else 0.0
        b_e = math.sqrt(1.0 - b_m**2 - b_s**2)
        s = 0.0
        if b_s:
            s = sectors.get(sector)
            if s is None:
                s = sectors[sector] = self._rng.gauss(0.0, 1.0)
        return b_m * market + b_s * s + b_e * self._rng.gauss(0.0, 1.0)
```

Notes:

- `add()` on an existing ticker returns its *current* price and doesn't reseed. Re-adding a ticker you just removed *does* reseed it: known tickers go back to their seed price, unknown ones get a new random price. That's acceptable. Keeping a "last seen" memory would add state for little value.
- The order of RNG draws depends on dict insertion order, so the same seed plus the same add/remove sequence gives the same path.

---

## 5. `SimulatorDataSource` — async adapter

```python
# backend/app/market/simulator.py  (part 2)
import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from .cache import PriceCache
from .interface import MarketDataSource

log = logging.getLogger(__name__)


class SimulatorDataSource(MarketDataSource):
    """Runs GBMSimulator on a fixed cadence and writes every ticker to the PriceCache each tick."""

    def __init__(
        self,
        cache: PriceCache,
        *,
        simulator: GBMSimulator | None = None,
        tick_seconds: float = 0.5,
    ) -> None:
        super().__init__(cache)
        self._tick_seconds = tick_seconds
        self._sim = simulator or GBMSimulator(tick_seconds=tick_seconds)
        self._task: asyncio.Task | None = None

    @property
    def tickers(self) -> frozenset[str]:
        return self._sim.tickers

    @property
    def name(self) -> str:
        return "simulator"

    async def start(self, tickers: Iterable[str]) -> None:
        for ticker in tickers:
            self._seed(ticker)                     # cache is full before the first SSE client connects
        self._task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._sim.tickers:
            self._seed(ticker)                     # priced immediately → a trade can fill right away

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove(ticker)
        self._cache.remove(ticker)

    def _seed(self, ticker: str) -> None:
        self._cache.update(ticker, self._sim.add(ticker))   # open_price := seed (first price this session)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            next_tick += self._tick_seconds        # fixed cadence: no drift from processing time
            await asyncio.sleep(max(0.0, next_tick - loop.time()))
            try:
                now = datetime.now(timezone.utc)
                for ticker, price in self._sim.step().items():
                    self._cache.update(ticker, price, timestamp=now)
            except Exception:                      # contract C7: never let the task die
                log.exception("Simulator tick failed")
```

How this meets the `MARKET_INTERFACE.md` contract:

| Contract | How |
|---|---|
| C1 (cache entry after `start`) | `start()` seeds synchronously, before the task starts |
| C2 (idempotent add) | `GBMSimulator.add` is idempotent; `add_ticker` skips known tickers |
| C3 (remove clears cache) | Removed from the simulator first, so `step()` never yields it again, then removed from the cache. No `await` in between |
| C4 (only tracked tickers written) | `step()` only iterates current states |
| C5 (timestamp changes per tick) | Every tick writes every ticker with the same `now` |
| C6 (idempotent stop) | `_task` is set to `None` after cancel |
| C7 (survives errors) | `try/except Exception` around each tick |

`UnknownTickerError` is never raised. Any format-valid ticker is accepted (`PLAN.md` §6).

### Behaviour across a session

- **`open_price`** is the seed price, set by the first `cache.update` without an explicit `open_price`. So `change_percent` is "since this server started", as `PLAN.md` §6 specifies. A **reset** (`POST /api/reset`) doesn't restart the simulator. Prices keep going, which is right: reset is about the portfolio, not the market.
- **Restarts** reseed everything. Positions bought at a simulated price will show P&L against a fresh seed after a container restart. This is a known and accepted quirk of a simulated market.
- Over very long uptimes (days), GBM wanders freely: at `time_scale = 10`, one real day ≈ ±10 % per ticker (1σ). That's fine for a demo. If it ever matters, add gentle mean reversion toward the seed price (Ornstein–Uhlenbeck on log price).

---

## 6. Configuration knobs

All are constructor arguments. Wire them to environment variables only if someone needs them.

| Parameter | Default | Effect |
|---|---|---|
| `tick_seconds` | `0.5` | Update cadence (`PLAN.md`: ~500 ms). Also sets Δt |
| `time_scale` | `10.0` | Market seconds per real second. Higher = more movement |
| `event_probability` | `0.0005` | Per ticker per tick |
| `event_range` | `(0.02, 0.05)` | Event size as a fraction |
| `rng` | `random.Random()` | Pass `random.Random(seed)` for deterministic tests |
| `MARKET_LOADING`, `SECTOR_LOADINGS` | 0.5 / per sector | Correlation structure (§2.3). Keep β_m² + β_k² ≤ 1 |

---

## 7. Verification and tests

The numbers in §2 were measured by running the code above with `random.Random(42)` for 28,800 ticks (4 hours of real time) with events off:

```
AAPL-MSFT corr 0.611  (target 0.61, same sector: tech)
JPM-V     corr 0.500  (target 0.50, same sector: finance)
AAPL-JPM  corr 0.246  (target 0.25, cross sector)
TSLA-AAPL corr 0.248  (target 0.25, TSLA market-only)
AAPL per-tick 0.023%  per-min 0.25%  per-hour 1.96%
events in 1 h across 10 tickers: 35 (expected ≈ 36)
```

The async adapter was smoke-tested with the `PriceCache` from `MARKET_INTERFACE.md`: seeding on start, `add_ticker` pricing immediately, `remove_ticker` clearing the cache, double `stop()`.

Unit tests to write (`backend/tests/market/test_simulator.py`), all on `GBMSimulator` with a seeded RNG unless noted:

| Test | Assertion |
|---|---|
| Seed prices | `add("AAPL") == 190.00`; unknown ticker seed in `[50, 300]` |
| Determinism | Two simulators with `Random(1)` give identical 100-step paths |
| Positivity | 100k steps with σ = 2.0 (extreme) → all prices > 0 |
| GBM moments | With events off, mean log-return per tick ≈ (μ − σ²/2)Δt and stdev ≈ σ√Δt (within 3 standard errors over 50k steps) |
| Correlation | Same-sector sample corr ≈ 0.61 ± 0.03; cross-sector ≈ 0.25 ± 0.03 |
| Events | `event_probability=1.0`, σ ≈ 0 → every step moves price by 2–5 % |
| No events | `event_probability=0` → max per-tick move < 1 % |
| Add/remove | `remove` → ticker absent from `step()` output; `add` twice → same state |
| Adapter (async) | After `start(["AAPL"])` the cache has AAPL at once; after ~3 ticks (`tick_seconds=0.01`) `previous_price` ≠ seed or direction is set; `remove_ticker` → not in cache after more ticks; `stop()` twice is fine |

Plus the shared `MarketDataSource` contract suite from `MARKET_INTERFACE.md` §13.
