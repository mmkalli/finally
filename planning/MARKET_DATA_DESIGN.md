# Market Data Backend — Detailed Design

The implementation-ready design for everything market data in the FinAlly backend: the unified API, the price cache, the GBM simulator, the Massive (Polygon.io) client, the SSE stream, and how the rest of the backend connects to them.

It implements `PLAN.md` §6 (Market Data) and the market-related parts of §5, §7, §8 and §12. It brings together and replaces the code in the three earlier research documents:

| Document | Role now |
|---|---|
| `MASSIVE_API.md` | Background: Massive endpoints, plans, response fields, gotchas. Still the reference for *why* the Massive client works the way it does. |
| `MARKET_SIMULATOR.md` | Background: derivation of the GBM maths, correlation model and tuning numbers. |
| `MARKET_INTERFACE.md` | Earlier version of this design. **Use this document instead** where they differ (see §15). |

**Status: verified.** Every code block in §3–§12 and §14 was put together as a real package and run: **54 pytest tests pass** (unit, contract suite against all three source variants, SSE framing, FastAPI route wiring). A live `uvicorn` run streamed correct SSE frames. Copy the code as it is; file paths are given at the top of each block.

---

## Contents

1. [Architecture](#1-architecture)
2. [Module layout and dependencies](#2-module-layout-and-dependencies)
3. [`PriceUpdate` — the price record](#3-priceupdate--the-price-record)
4. [`PriceCache`](#4-pricecache)
5. [Tickers and errors](#5-tickers-and-errors)
6. [`MarketDataSource` — the unified interface](#6-marketdatasource--the-unified-interface)
7. [Simulator](#7-simulator)
8. [Massive API client](#8-massive-api-client)
9. [Factory and environment variables](#9-factory-and-environment-variables)
10. [The priced set and route integration](#10-the-priced-set-and-route-integration)
11. [SSE endpoint](#11-sse-endpoint)
12. [App wiring](#12-app-wiring)
13. [Usage examples](#13-usage-examples)
14. [Tests](#14-tests)
15. [Departures from `PLAN.md` and changes from `MARKET_INTERFACE.md`](#15-departures-from-planmd-and-changes-from-market_interfacemd)
16. [Implementation checklist](#16-implementation-checklist)

---

## 1. Architecture

```
                       ┌──────────────────────────── backend process (one asyncio event loop) ────────────────────────────┐
                       │                                                                                                  │
 MASSIVE_API_KEY set?  │  create_market_data_source(cache)                                                                │
        │              │        │                                                                                         │
        ├── no ──────────▶ SimulatorDataSource ──┐ every 500 ms: writes                                                  │
        │              │   (GBMSimulator)        │ every ticker                                                           │
        │              │                         ├──────────▶  PriceCache  ◀── read ── SSE  GET /api/stream/prices        │
        └── yes ─────────▶ MassiveDataSource ────┘ on poll: writes             ◀── read ── GET /api/watchlist            │
                       │   (snapshot | eod mode)   only changed tickers        ◀── read ── trade execution (fill price)  │
                       │                                                       ◀── read ── portfolio valuation           │
                       │                                                       ◀── read ── LLM portfolio context         │
                       │                                                                                                  │
                       │  watchlist / trade / chat / reset routes ── add_ticker() / sync_priced_tickers() ──▶ source      │
                       └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Design rules:

1. **One writer.** Only the active data source writes to the `PriceCache`. Everything else only reads it.
2. **The source tracks the priced set; the routes decide it.** The priced set is *watchlist ∪ open positions* (`PLAN.md` §6). After any change, routes call `sync_priced_tickers()`.
3. **Single event loop, no thread locks.** Both sources are asyncio tasks. `PriceCache` methods never `await`, so they are atomic with respect to other coroutines.
4. **Nobody waits for a price.** A ticker with no cached price gives `NO_PRICE` for trades and `null` fields in the watchlist. Sources try to price a ticker *as it is added*, so in practice the gap is zero for the simulator and paid Massive plans.
5. **Downstream code doesn't know the source.** SSE, portfolio and LLM code use only `PriceCache` and `PriceUpdate`.

---

## 2. Module layout and dependencies

```
backend/
├── pyproject.toml
├── app/
│   ├── main.py                 # lifespan: init DB → start source; error handler; routers; static mount
│   └── market/
│       ├── __init__.py         # public API (re-exports)
│       ├── models.py           # PriceUpdate, format_timestamp, EMPTY_PRICE_FIELDS
│       ├── cache.py            # PriceCache
│       ├── tickers.py          # normalize_ticker, MarketDataError, InvalidTickerError, UnknownTickerError
│       ├── interface.py        # MarketDataSource (ABC) + sync()
│       ├── seed_data.py        # TickerProfile, PROFILES, loadings, DEFAULT_TICKERS, profile_for()
│       ├── simulator.py        # GBMSimulator (pure maths) + SimulatorDataSource (async adapter)
│       ├── massive.py          # MassiveDataSource (+ pure parsing helpers)
│       ├── factory.py          # create_market_data_source()
│       ├── priced.py           # load_priced_tickers(), sync_priced_tickers()
│       ├── stream.py           # SSE router: GET /api/stream/prices
│       └── demo.py             # `python -m app.market.demo` — watch prices in a terminal
└── tests/
    └── market/
        ├── fake_massive.py     # httpx.MockTransport fake of the Massive API
        ├── test_cache_and_tickers.py
        ├── test_simulator.py
        ├── test_massive.py
        ├── test_contract.py    # shared suite run against every source
        └── test_stream.py
```

Dependency direction (no cycles): `models ← cache ← interface ← {simulator, massive} ← factory`; `tickers` is used by `interface` and `massive`; `stream` and `priced` depend only on `cache` / `interface`.

### `pyproject.toml` (market-data relevant parts)

```toml
[project]
name = "finally-backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",          # Massive client (async). Listed explicitly even though LiteLLM also pulls it in.
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

The simulator uses only the standard library (`math`, `random`, `asyncio`). With 10–30 tickers a plain loop takes microseconds, so **no numpy**. The Massive client uses `httpx.AsyncClient` directly, not the official `massive` package (reasons in `MASSIVE_API.md` §6: native async, real HTTP status codes, and no hidden retries spending the free-tier budget).

### Public API — `app/market/__init__.py`

```python
# backend/app/market/__init__.py
from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .massive import MassiveDataSource
from .models import EMPTY_PRICE_FIELDS, PriceUpdate
from .priced import load_priced_tickers, sync_priced_tickers
from .simulator import GBMSimulator, SimulatorDataSource
from .stream import stream_router
from .tickers import InvalidTickerError, MarketDataError, UnknownTickerError, normalize_ticker

__all__ = [
    "EMPTY_PRICE_FIELDS", "GBMSimulator", "InvalidTickerError", "MarketDataError", "MarketDataSource",
    "MassiveDataSource", "PriceCache", "PriceUpdate", "SimulatorDataSource", "UnknownTickerError",
    "create_market_data_source", "load_priced_tickers", "normalize_ticker", "stream_router",
    "sync_priced_tickers",
]
```

---

## 3. `PriceUpdate` — the price record

One immutable record per ticker. `change_percent` and `direction` are worked out from the stored fields, so they can never disagree with them. `to_dict()` produces exactly the per-ticker JSON from `PLAN.md` §6 / §8.

```python
# backend/app/market/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Direction = Literal["up", "down", "flat"]


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable price record for one ticker. Same shape as the SSE / watchlist JSON (PLAN.md §6, §8)."""

    ticker: str
    price: float
    previous_price: float
    open_price: float
    timestamp: datetime  # timezone-aware UTC

    @property
    def change_percent(self) -> float:
        if self.open_price == 0:
            return 0.0
        return round((self.price - self.open_price) / self.open_price * 100, 2)

    @property
    def direction(self) -> Direction:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "open_price": self.open_price,
            "change_percent": self.change_percent,
            "direction": self.direction,
            "timestamp": format_timestamp(self.timestamp),
        }


def format_timestamp(ts: datetime) -> str:
    """ISO 8601 UTC with milliseconds and a trailing Z, e.g. 2026-10-12T14:03:21.512Z."""
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")


EMPTY_PRICE_FIELDS: dict = {
    "price": None, "previous_price": None, "open_price": None,
    "change_percent": None, "direction": None, "timestamp": None,
}
```

`EMPTY_PRICE_FIELDS` is what `GET /api/watchlist` uses for a ticker that hasn't been priced yet ("price fields are `null`", `PLAN.md` §8).

---

## 4. `PriceCache`

```python
# backend/app/market/cache.py
from __future__ import annotations

from datetime import datetime, timezone

from .models import PriceUpdate


class PriceCache:
    """Latest price per ticker. One writer (the active MarketDataSource), many readers.

    Everything runs on the event loop and no method awaits, so no lock is needed.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._version = 0  # bumped on every write so readers can skip work when nothing changed

    # ---- writes (data source only) ----

    def update(
        self,
        ticker: str,
        price: float,
        *,
        timestamp: datetime | None = None,
        open_price: float | None = None,
    ) -> PriceUpdate:
        """Record a new price for `ticker`.

        previous_price = the price before this update (this price, on first sight)
        open_price     = the explicit value if given (Massive: previous close),
                         else the existing open_price, else this price (simulator: first price this session)
        """
        prev = self._prices.get(ticker)
        price = round(price, 2)
        if open_price is None:
            open_price = prev.open_price if prev else price
        update = PriceUpdate(
            ticker=ticker,
            price=price,
            previous_price=prev.price if prev else price,
            open_price=round(open_price, 2),
            timestamp=timestamp or datetime.now(timezone.utc),
        )
        self._prices[ticker] = update
        self._version += 1
        return update

    def remove(self, ticker: str) -> None:
        if self._prices.pop(ticker, None) is not None:
            self._version += 1

    # ---- reads ----

    def get(self, ticker: str) -> PriceUpdate | None:
        return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        update = self._prices.get(ticker)
        return update.price if update else None

    def snapshot(self) -> dict[str, PriceUpdate]:
        """Shallow copy, safe to iterate while the source keeps writing."""
        return dict(self._prices)

    @property
    def version(self) -> int:
        return self._version

    def __contains__(self, ticker: object) -> bool:
        return ticker in self._prices

    def __len__(self) -> int:
        return len(self._prices)
```

Semantics, matching `PLAN.md` §6 "Shared Price Cache":

| Field | Simulator | Massive |
|---|---|---|
| `price` | latest GBM value, rounded to 2 dp | latest trade / minute / day close (§8.3) |
| `previous_price` | value at the previous tick | value at the previous *changed* poll |
| `open_price` | first price this session (seed): `open_price` is never passed | previous day's close (`prevDay.c` or the prior grouped-daily close), passed explicitly |
| `timestamp` | wall-clock time of the tick | `updated` from the snapshot, or the daily bar's time |

`version` is a monotonic counter. The SSE loop compares it to skip ticks where nothing changed, without building a snapshot.

---

## 5. Tickers and errors

```python
# backend/app/market/tickers.py
import re

TICKER_RE = re.compile(r"^[A-Z.]{1,6}$")


class MarketDataError(ValueError):
    """Base for market-data errors that map to the API error shape {"error", "code"} (PLAN.md §8)."""

    code = "MARKET_ERROR"
    http_status = 400


class InvalidTickerError(MarketDataError):
    code = "INVALID_TICKER"


class UnknownTickerError(MarketDataError):
    """The data source knows this ticker doesn't exist. Raised by Massive only."""

    code = "UNKNOWN_TICKER"


def normalize_ticker(raw: object) -> str:
    """Trim + uppercase, then validate (PLAN.md §6 'Ticker Validation')."""
    ticker = raw.strip().upper() if isinstance(raw, str) else ""
    if not TICKER_RE.fullmatch(ticker):
        raise InvalidTickerError(f"Invalid ticker: {raw!r}")
    return ticker
```

- Every entry point (watchlist routes, trade route, chat action executor) calls `normalize_ticker()` **first**. Data sources only ever see normalized tickers.
- `MarketDataError` carries `code` and `http_status`, so one FastAPI exception handler (§12) turns both errors into the standard `{"error", "code"}` response from `PLAN.md` §8. In the chat flow the executor catches `MarketDataError` and records `status: "error", "error": str(e), "code": e.code` on the action instead.
- `NO_PRICE` is not a market-data exception. It is decided by the trade code when `cache.get_price()` returns `None` (§10).

---

## 6. `MarketDataSource` — the unified interface

```python
# backend/app/market/interface.py
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable

from .cache import PriceCache
from .tickers import UnknownTickerError

log = logging.getLogger(__name__)


class MarketDataSource(ABC):
    """Produces prices for a changing set of tickers and writes them into a PriceCache.

    Lifecycle: start() once in the FastAPI lifespan, add/remove tickers at runtime, stop() on shutdown.
    Every method takes tickers already normalized by normalize_ticker().
    """

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache

    @property
    def cache(self) -> PriceCache:
        return self._cache

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Begin pricing `tickers` in a background task. Returns quickly (no long network waits)."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel background work and release resources. Idempotent."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start pricing `ticker`. Idempotent.

        Puts a first price in the cache before returning when it can do so cheaply.
        Raises UnknownTickerError if the source knows the ticker doesn't exist.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Stop pricing `ticker` and drop it from the cache. Idempotent."""

    @property
    @abstractmethod
    def tickers(self) -> frozenset[str]:
        """Tickers currently being priced."""

    @property
    def name(self) -> str:
        """For logs, e.g. 'simulator' or 'massive:snapshot'."""
        return type(self).__name__

    async def sync(self, desired: Iterable[str]) -> None:
        """Make the priced set equal `desired`. Best-effort: tickers the source can't price are skipped."""
        desired = set(desired)
        current = self.tickers
        for ticker in sorted(desired - current):
            try:
                await self.add_ticker(ticker)
            except UnknownTickerError:
                log.warning("Not pricing unknown ticker %s", ticker)
        for ticker in sorted(current - desired):
            await self.remove_ticker(ticker)
```

### Contract (enforced by the shared suite in §14)

| # | Behaviour |
|---|---|
| C1 | After `start(T)`, every ticker in `T` that the source can price gets a cache entry within one update interval. The simulator does it before `start` returns. |
| C2 | `add_ticker(t)` is idempotent; afterwards `t in source.tickers`. |
| C3 | `remove_ticker(t)` removes `t` from `source.tickers` **and** the cache, and later updates never bring it back, even if a request was in flight. |
| C4 | The cache only ever holds tickers in `source.tickers`. |
| C5 | A ticker's `timestamp` changes only when a tick happened (simulator) or its data actually changed (Massive). |
| C6 | `stop()` is idempotent and leaves no running task. |
| C7 | Network/API failures and bad responses never kill the background task. The last known prices stay in the cache. |

`sync()` adds before it removes. A failed add (unknown ticker) is logged and skipped, so `sync` never fails halfway. User-facing validation happens earlier, in the watchlist route's `add_ticker` call.

---

## 7. Simulator

### 7.1 Model (summary; derivation in `MARKET_SIMULATOR.md` §2)

**GBM step**, exact solution over Δt, so prices can never go to or below zero:

```
S(t+Δt) = S(t) · exp( (μ − σ²/2)·Δt + σ·√Δt·Z )
```

**Time compression.** Δt is in trading years (252 × 6.5 h = 5,896,800 s). `time_scale = 10` makes one real second cover ten market seconds, so movement is visible on every tick:

| Ticker (σ) | Typical move per 500 ms tick | per minute | per hour |
|---|---|---|---|
| V (18 %) | 0.017 % | 0.18 % | 1.4 % |
| AAPL (25 %) | 0.023 % (~4 ¢) | 0.25 % | 2.0 % |
| TSLA (55 %) | 0.051 % | 0.55 % | 4.3 % |

**Correlation: a factor model.** Each tick draws one market shock M, one shock S_k per sector, and one idiosyncratic εᵢ per ticker:

```
Zᵢ = β_m·M + β_k·S_k + √(1 − β_m² − β_k²)·εᵢ        ⇒  Var(Zᵢ) = 1
corr(i, j) = β_m² + β_k²  (same sector)    β_m²  (otherwise)
```

| Loading | Value | Correlation |
|---|---|---|
| Market β_m | 0.5 | 0.25 between any two tickers |
| Tech | 0.6 | 0.61 within AAPL, GOOGL, MSFT, NVDA, META, AMD, INTC |
| Finance | 0.5 | 0.50 within JPM, V, BAC, GS |
| Consumer | 0.4 | 0.41 within AMZN, NFLX, DIS |
| None (TSLA, unknown tickers) | — | 0.25 (market only) |

It's always a valid correlation structure (no Cholesky to break), adding or removing tickers costs nothing, and it is O(n) per tick.

**Events.** Each ticker, each tick, has probability 0.0005 of a jump of ±U(2 %, 5 %). That's about one per ticker every 17 minutes, ≈ 36/hour across the 10 defaults, so there's usually some drama within a couple of minutes.

### 7.2 Seed data — `seed_data.py`

```python
# backend/app/market/seed_data.py
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TickerProfile:
    seed_price: float
    drift: float        # annualized mu
    volatility: float   # annualized sigma
    sector: str | None  # tickers in the same sector share a sector shock


MARKET_LOADING = 0.5
SECTOR_LOADINGS: dict[str, float] = {"tech": 0.6, "finance": 0.5, "consumer": 0.4}
# Keep MARKET_LOADING**2 + loading**2 <= 1 for every sector.

PROFILES: dict[str, TickerProfile] = {
    "AAPL":  TickerProfile(190.00, 0.08, 0.25, "tech"),
    "GOOGL": TickerProfile(175.00, 0.08, 0.28, "tech"),
    "MSFT":  TickerProfile(420.00, 0.08, 0.24, "tech"),
    "AMZN":  TickerProfile(185.00, 0.09, 0.30, "consumer"),
    "TSLA":  TickerProfile(250.00, 0.05, 0.55, None),
    "NVDA":  TickerProfile(130.00, 0.12, 0.45, "tech"),
    "META":  TickerProfile(500.00, 0.09, 0.35, "tech"),
    "JPM":   TickerProfile(200.00, 0.06, 0.20, "finance"),
    "V":     TickerProfile(280.00, 0.07, 0.18, "finance"),
    "NFLX":  TickerProfile(650.00, 0.08, 0.38, "consumer"),
    # Extras so common watchlist additions start at believable levels
    "AMD":   TickerProfile(160.00, 0.10, 0.45, "tech"),
    "INTC":  TickerProfile(35.00, 0.03, 0.35, "tech"),
    "BAC":   TickerProfile(40.00, 0.06, 0.25, "finance"),
    "GS":    TickerProfile(450.00, 0.06, 0.25, "finance"),
    "DIS":   TickerProfile(100.00, 0.06, 0.28, "consumer"),
}

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
DEFAULT_DRIFT = 0.05
DEFAULT_VOLATILITY = 0.30
UNKNOWN_PRICE_RANGE = (50.0, 300.0)


def profile_for(ticker: str, rng: random.Random) -> TickerProfile:
    """Known ticker -> its profile. Unknown valid ticker -> random $50-$300 seed, default mu/sigma, no sector."""
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

`DEFAULT_TICKERS` matches the database seed in `PLAN.md` §7. The database module should import it rather than repeating the list.

### 7.3 `GBMSimulator` and `SimulatorDataSource` — `simulator.py`

```python
# backend/app/market/simulator.py
from __future__ import annotations

import asyncio
import logging
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from .cache import PriceCache
from .interface import MarketDataSource
from .seed_data import MARKET_LOADING, SECTOR_LOADINGS, TickerProfile, profile_for

log = logging.getLogger(__name__)

TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800


@dataclass(slots=True)
class _State:
    price: float  # full precision; only the cache rounds
    profile: TickerProfile


class GBMSimulator:
    """Correlated geometric Brownian motion with random jump events.

    Pure and synchronous: no asyncio, no clock, no cache. Deterministic for a seeded rng.
    """

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
        self._sqrt_dt = math.sqrt(self._dt)
        self._event_probability = event_probability
        self._event_range = event_range
        self._states: dict[str, _State] = {}

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

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick. Returns {ticker: new_price}."""
        rng = self._rng
        market = rng.gauss(0.0, 1.0)
        sector_shocks: dict[str, float] = {}  # drawn lazily, once per sector per tick
        out: dict[str, float] = {}
        for ticker, state in self._states.items():
            p = state.profile
            z = self._shock(p.sector, market, sector_shocks)
            log_return = (p.drift - 0.5 * p.volatility**2) * self._dt + p.volatility * self._sqrt_dt * z
            price = state.price * math.exp(log_return)
            if rng.random() < self._event_probability:
                move = rng.uniform(*self._event_range)
                price *= (1 + move) if rng.random() < 0.5 else (1 - move)
            state.price = price
            out[ticker] = price
        return out

    def _shock(self, sector: str | None, market: float, sector_shocks: dict[str, float]) -> float:
        """Z = b_m*M + b_s*S_sector + sqrt(1 - b_m^2 - b_s^2)*eps  ->  Var(Z) = 1."""
        b_m = MARKET_LOADING
        b_s = SECTOR_LOADINGS.get(sector, 0.0) if sector else 0.0
        s = 0.0
        if b_s:
            s = sector_shocks.get(sector)
            if s is None:
                s = sector_shocks[sector] = self._rng.gauss(0.0, 1.0)
        b_e = math.sqrt(1.0 - b_m**2 - b_s**2)
        return b_m * market + b_s * s + b_e * self._rng.gauss(0.0, 1.0)


class SimulatorDataSource(MarketDataSource):
    """Runs GBMSimulator every tick_seconds and writes every ticker to the cache."""

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
            self._seed(ticker)  # cache is full before the first SSE client connects
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._sim.tickers:
            self._seed(ticker)  # priced immediately, so a trade can fill at once

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove(ticker)  # first, so the next step() can't bring it back
        self._cache.remove(ticker)

    def _seed(self, ticker: str) -> None:
        self._cache.update(ticker, self._sim.add(ticker))  # open_price := seed price

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            next_tick += self._tick_seconds  # fixed cadence, no drift from processing time
            delay = next_tick - loop.time()
            if delay < -self._tick_seconds:  # fell far behind (host slept): resync, don't burst
                next_tick, delay = loop.time(), 0.0
            await asyncio.sleep(max(0.0, delay))
            try:
                now = datetime.now(timezone.utc)
                for ticker, price in self._sim.step().items():
                    self._cache.update(ticker, price, timestamp=now)
            except Exception:  # contract C7: the task never dies
                log.exception("Simulator tick failed")
```

Behaviour notes:

- **Pure core, thin adapter.** `GBMSimulator` has no clock, cache or asyncio. Tests drive `step()` in a loop with `random.Random(seed)` and get exactly reproducible paths.
- **Full precision inside.** Only the cache rounds to 2 dp. Rounding in the simulator would bias small moves and could freeze a price.
- **`add_ticker` prices immediately.** So a manual or AI trade on a newly added ticker can fill on the same request. The simulator never raises `UnknownTickerError` (`PLAN.md` §6: any valid-format ticker is accepted).
- **Fixed cadence with resync.** Ticks are scheduled from `loop.time()`, so processing time doesn't add drift. If the host was suspended, the loop skips ahead instead of firing a burst of catch-up ticks.
- **Reset doesn't restart the market.** `POST /api/reset` changes the portfolio and watchlist, and `sync()` drops tickers that are no longer priced. Tickers that remain keep their current price and session `open_price`.
- **Re-adding a removed ticker reseeds it.** Known tickers go back to their seed price; unknown ones get a new random price. That's accepted: keeping memory of removed tickers would add state for little value.
- **Restarts reseed everything.** Positions then show P&L against fresh seeds. That's a known quirk of a simulated market.

### 7.4 Contract mapping

| Contract | How the simulator meets it |
|---|---|
| C1 | `start()` seeds synchronously, before creating the task |
| C2 | `GBMSimulator.add` is idempotent; `add_ticker` skips tickers it already tracks |
| C3 | Removed from the simulator first, then from the cache, with no `await` in between, so no tick can re-insert it |
| C4 | `step()` only iterates current states |
| C5 | Every tick writes every ticker with one shared `now` |
| C6 | `_task` is cleared after the cancel |
| C7 | `try/except Exception` around each tick |

---

## 8. Massive API client

### 8.1 What the plan allows (from `MASSIVE_API.md` §2)

| Plan | Snapshot endpoint | Data recency | Rate limit | FinAlly mode |
|---|---|---|---|---|
| Basic (free) | ❌ 403 | end of day only | 5 calls / min | **eod** |
| Starter / Developer | ✅ | 15-min delayed | unlimited | **snapshot** |
| Advanced | ✅ | real time | unlimited | **snapshot** |

The free plan **cannot** give intraday prices, so polling it every 15 s (as `PLAN.md` §6 suggests) would only get 403s. The client therefore **detects the plan** on its first call and picks a mode.

### 8.2 Endpoints used

| Mode | Call | Purpose |
|---|---|---|
| detect | `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=<one>` | 200 → snapshot mode, 403 → eod mode |
| snapshot | `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,…` | every priced ticker in one call (100 per chunk) |
| eod | `GET /v2/aggs/grouped/locale/us/market/stocks/{YYYY-MM-DD}?adjusted=true` | every US close for one day in one call |

Auth: `Authorization: Bearer <MASSIVE_API_KEY>` header (keeps the key out of URLs and logs).

Example snapshot item (trimmed) and how it maps:

```json
{"ticker": "AAPL", "updated": 1760278401512000000,
 "day": {"c": 190.12}, "prevDay": {"c": 188.50}, "min": {"c": 190.12},
 "lastTrade": {"p": 190.12}}
```
→ `cache.update("AAPL", 190.12, timestamp=2025-10-12T14:13:21.512Z, open_price=188.50)` → `change_percent = 0.86`.

### 8.3 Parsing rules

- **Price:** `lastTrade.p` → `min.c` → `day.c`, skipping missing and zero values. `lastTrade` exists only on Developer+.
- **`prevDay.c` only for the very first price.** Massive clears snapshot data around 3:30–4:00 AM ET, and `day`/`min` read `0` during that window. Falling back to the previous close there would make the price jump back to yesterday and then forward again. So once a ticker has a cached price, a zeroed item is skipped.
- **`open_price`** = `prevDay.c` (snapshot) or the previous trading day's close (eod), per `PLAN.md` §6.
- **Change detection:** a ticker is written only when its `updated` (snapshot) or trading day (eod) differs from the last one written. So with Massive most SSE ticks have nothing to send and are skipped, as `PLAN.md` §6 expects.
- **Unknown tickers:** the snapshot simply leaves them out of `tickers[]` (no error). Grouped-daily data doesn't contain them.
- **Timestamps:** `updated` is in **nanoseconds**; grouped-daily `t` is in **milliseconds**.

### 8.4 Code — `massive.py`

```python
# backend/app/market/massive.py
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from .cache import PriceCache
from .interface import MarketDataSource
from .tickers import UnknownTickerError

log = logging.getLogger(__name__)

BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
GROUPED_PATH = "/v2/aggs/grouped/locale/us/market/stocks/{day}"
NY = ZoneInfo("America/New_York")
EOD_PUBLISH_TIME = dtime(16, 15)  # ET; don't look for today's daily bars before this

Mode = Literal["snapshot", "eod"]


# ----------------------------------------------------------------------------- pure helpers

def _positive(x: object) -> float | None:
    if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0:
        return float(x)
    return None


def pick_price(item: dict, *, allow_prev_close: bool) -> float | None:
    """Most specific non-zero price in a snapshot item: lastTrade.p -> min.c -> day.c (-> prevDay.c).

    prevDay.c is only allowed for a ticker's first price: during the ~3:30-4:00 AM ET reset, day/min
    are zero and falling back to the previous close would make the price jump back to yesterday.
    """
    price = (
        _positive((item.get("lastTrade") or {}).get("p"))
        or _positive((item.get("min") or {}).get("c"))
        or _positive((item.get("day") or {}).get("c"))
    )
    if price is None and allow_prev_close:
        price = _positive((item.get("prevDay") or {}).get("c"))
    return price


def ns_to_datetime(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


def previous_weekday(day: date, *, inclusive: bool = False) -> date:
    if not inclusive:
        day -= timedelta(days=1)
    while day.weekday() >= 5:  # Sat/Sun
        day -= timedelta(days=1)
    return day


def latest_published_day(now_ny: datetime) -> date:
    """Most recent weekday whose end-of-day bars could be published by `now_ny`."""
    day = now_ny.date()
    if now_ny.time() < EOD_PUBLISH_TIME:
        day -= timedelta(days=1)
    return previous_weekday(day, inclusive=True)


@dataclass(frozen=True, slots=True)
class EodData:
    day: date                       # latest trading day with data
    closes: dict[str, float]        # ticker -> close on `day`
    prior_closes: dict[str, float]  # ticker -> close on the trading day before `day`
    timestamp: datetime             # bar time for `day` (UTC)


# ----------------------------------------------------------------------------- data source

class MassiveDataSource(MarketDataSource):
    """Polls the Massive REST API. Auto-detects the plan on the first poll:

    - snapshot mode (paid plans): one multi-ticker snapshot call every poll_interval seconds
    - eod mode (free plan, snapshot -> 403): grouped-daily closes, refreshed after each close,
      throttled to 5 calls per rolling minute
    """

    EOD_REFRESH_SECONDS = 300.0
    FREE_TIER_CALLS_PER_MINUTE = 5
    SNAPSHOT_CHUNK = 100     # tickers per snapshot request, keeps URLs short
    READY_TIMEOUT = 10.0     # how long add_ticker waits for the first poll
    MAX_WALKBACK = 7         # weekdays searched for the two latest closes (covers holiday clusters)

    def __init__(
        self,
        cache: PriceCache,
        *,
        api_key: str,
        poll_interval: float = 15.0,
        client: httpx.AsyncClient | None = None,          # inject httpx.MockTransport clients in tests
        now: Callable[[], datetime] = lambda: datetime.now(NY),
    ) -> None:
        super().__init__(cache)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        self._poll_interval = poll_interval
        self._now = now
        self._tickers: set[str] = set()
        self._mode: Mode | None = None
        self._last_seen: dict[str, object] = {}  # ticker -> `updated` (snapshot) or trading day (eod)
        self._eod: EodData | None = None
        self._ready = asyncio.Event()            # set after the first successful poll
        self._dead = False                       # key rejected; poller has stopped
        self._call_times: deque[float] = deque()
        self._throttle_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._closed = False

    # ------------------------------------------------------------------ interface

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._tickers)

    @property
    def name(self) -> str:
        return f"massive:{self._mode or 'detecting'}"

    async def start(self, tickers: Iterable[str]) -> None:
        self._tickers.update(tickers)
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="massive-poller")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._owns_client and not self._closed:
            self._closed = True
            await self._client.aclose()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        if not self._dead and not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=self.READY_TIMEOUT)
            except TimeoutError:
                pass
        if not self._ready.is_set():
            # API slow, unreachable or key rejected: accept unvalidated rather than block the user.
            log.warning("Massive has no data yet; adding %s without validation", ticker)
            self._tickers.add(ticker)
            return

        if self._mode == "eod":
            if self._eod is None or ticker not in self._eod.closes:
                raise UnknownTickerError(f"Unknown ticker: {ticker}")
            self._tickers.add(ticker)
            self._apply_eod(ticker)
            return

        try:
            items = await self._fetch_snapshot([ticker])
        except httpx.HTTPError as e:
            log.warning("Could not validate %s (%r); adding without validation", ticker, e)
            self._tickers.add(ticker)
            return
        item = next((i for i in items if i.get("ticker") == ticker), None)
        if item is None:
            raise UnknownTickerError(f"Unknown ticker: {ticker}")
        self._tickers.add(ticker)
        self._apply_snapshot(item)

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._last_seen.pop(ticker, None)
        self._cache.remove(ticker)

    # ------------------------------------------------------------------ poll loop

    async def _run(self) -> None:
        delay = 0.0
        while True:
            await asyncio.sleep(delay)
            try:
                await self._poll_once()
                self._ready.set()
                delay = self._poll_interval if self._mode == "snapshot" else self.EOD_REFRESH_SECONDS
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 401:
                    log.error("MASSIVE_API_KEY was rejected (401). No prices will stream. "
                              "Fix the key, or unset it to use the simulator.")
                    self._dead = True
                    return
                if status == 403 and self._mode == "snapshot":
                    log.warning("Snapshot access lost (403); re-detecting plan")
                    self._mode = None
                log.warning("Massive poll failed with HTTP %s; retrying", status)
                delay = 60.0 if status == 429 else self._retry_delay()
            except httpx.HTTPError as e:
                log.warning("Massive poll failed: %r; retrying", e)
                delay = self._retry_delay()
            except Exception:  # contract C7: the poller never dies on a bad response
                log.exception("Unexpected error in Massive poller")
                delay = self._retry_delay()

    def _retry_delay(self) -> float:
        return max(self._poll_interval, 5.0) if self._mode == "snapshot" else 60.0

    async def _poll_once(self) -> None:
        if self._mode is None:
            self._mode = await self._detect_mode()
            log.info("Massive plan detected: %s mode", self._mode)
        if self._mode == "snapshot":
            await self._poll_snapshot()
        else:
            await self._poll_eod()

    async def _detect_mode(self) -> Mode:
        probe = min(self._tickers, default="AAPL")
        resp = await self._get(SNAPSHOT_PATH, {"tickers": probe}, raise_for_status=False)
        if resp.status_code == 403:
            return "eod"
        resp.raise_for_status()  # 401 / 429 / 5xx go to _run's handlers
        return "snapshot"

    # ------------------------------------------------------------------ snapshot mode

    async def _poll_snapshot(self) -> None:
        if self._tickers:
            for item in await self._fetch_snapshot(sorted(self._tickers)):
                self._apply_snapshot(item)

    async def _fetch_snapshot(self, tickers: list[str]) -> list[dict]:
        items: list[dict] = []
        for i in range(0, len(tickers), self.SNAPSHOT_CHUNK):
            chunk = tickers[i : i + self.SNAPSHOT_CHUNK]
            resp = await self._get(SNAPSHOT_PATH, {"tickers": ",".join(chunk)})
            items.extend(resp.json().get("tickers") or [])
        return items

    def _apply_snapshot(self, item: dict) -> None:
        ticker = item.get("ticker")
        if ticker not in self._tickers:  # removed while the request was in flight (C3/C4)
            return
        updated = item.get("updated")
        if not updated or self._last_seen.get(ticker) == updated:  # unchanged -> no write (C5)
            return
        price = pick_price(item, allow_prev_close=ticker not in self._cache)
        if price is None:
            return
        self._cache.update(
            ticker,
            price,
            timestamp=ns_to_datetime(updated),
            open_price=_positive((item.get("prevDay") or {}).get("c")),
        )
        self._last_seen[ticker] = updated

    # ------------------------------------------------------------------ eod mode (free plan)

    async def _poll_eod(self) -> None:
        target = latest_published_day(self._now())
        if self._eod is None:
            self._eod = await self._load_latest_two(target)
        elif target > self._eod.day:
            fetched = await self._fetch_grouped(target)  # empty until published / on holidays
            if fetched is not None:
                closes, ts = fetched
                self._eod = EodData(target, closes, self._eod.closes, ts)
        for ticker in list(self._tickers):
            self._apply_eod(ticker)

    async def _load_latest_two(self, day: date) -> EodData:
        found: list[tuple[date, dict[str, float], datetime]] = []
        for _ in range(self.MAX_WALKBACK):
            fetched = await self._fetch_grouped(day)
            if fetched is not None:
                found.append((day, *fetched))
                if len(found) == 2:
                    break
            day = previous_weekday(day)
        if not found:
            raise RuntimeError("No grouped-daily data in the last %d weekdays" % self.MAX_WALKBACK)
        latest_day, closes, ts = found[0]
        prior = found[1][1] if len(found) > 1 else {}
        return EodData(latest_day, closes, prior, ts)

    async def _fetch_grouped(self, day: date) -> tuple[dict[str, float], datetime] | None:
        resp = await self._get(GROUPED_PATH.format(day=day.isoformat()), {"adjusted": "true"})
        results = resp.json().get("results") or []
        closes = {r["T"]: float(r["c"]) for r in results if r.get("T") and _positive(r.get("c"))}
        if not closes:
            return None
        ts = datetime.fromtimestamp(max(r.get("t", 0) for r in results) / 1000, tz=timezone.utc)
        return closes, ts

    def _apply_eod(self, ticker: str) -> None:
        eod = self._eod
        if eod is None or ticker not in eod.closes or self._last_seen.get(ticker) == eod.day:
            return
        self._cache.update(
            ticker,
            eod.closes[ticker],
            timestamp=eod.timestamp,
            open_price=eod.prior_closes.get(ticker),  # None -> the close itself (0 % change)
        )
        self._last_seen[ticker] = eod.day

    # ------------------------------------------------------------------ http

    async def _get(self, path: str, params: dict, *, raise_for_status: bool = True) -> httpx.Response:
        if self._mode != "snapshot":  # free plan (or not yet known): respect 5 calls/min
            await self._throttle()
        resp = await self._client.get(path, params=params)
        if raise_for_status:
            resp.raise_for_status()
        return resp

    async def _throttle(self) -> None:
        """At most FREE_TIER_CALLS_PER_MINUTE calls in any rolling 60 s window."""
        async with self._throttle_lock:
            while True:
                now = time.monotonic()
                while self._call_times and now - self._call_times[0] >= 60.0:
                    self._call_times.popleft()
                if len(self._call_times) < self.FREE_TIER_CALLS_PER_MINUTE:
                    self._call_times.append(now)
                    return
                await asyncio.sleep(60.0 - (now - self._call_times[0]) + 0.05)
```

### 8.5 Behaviour over time

**Paid key** (snapshot mode, `MASSIVE_POLL_INTERVAL=15`):

```
t=0      start()         → task created, returns immediately
t≈0.2s   detect call     → 200 → snapshot mode
t≈0.4s   snapshot call   → all priced tickers written → _ready set → SSE sends the full set
t=15s    snapshot call   → only tickers whose `updated` changed are written
...      add_ticker(X)   → one snapshot call for X: missing → UNKNOWN_TICKER; present → priced at once
```

**Free key** (eod mode), Monday evening after close:

```
t=0      detect call     → 403 → eod mode                                  (call 1 of 5 this minute)
         grouped Mon     → closes                                          (call 2)
         grouped Fri     → prior closes (weekend skipped, no calls)        (call 3)
         → every ticker written: price = Mon close, open_price = Fri close → _ready set
+5 min   refresh: latest publishable day is still Mon → no call
Tue 16:15 ET+  refresh   → grouped Tue (one call; empty until published, retried every 5 min)
add_ticker(X)            → looked up in cached closes, no API call; missing → UNKNOWN_TICKER
```

A free key costs about **3–5 calls at startup and 1 call per trading day** afterwards (plus one call every 5 min on a market holiday, until the next trading day). Prices stay still intraday on a free key. That is correct, and the README should say so and point users who want movement to the simulator or a paid plan.

### 8.6 Failure handling

| Situation | Behaviour |
|---|---|
| 401 (bad key) | Logs one clear error and the poller stops. `add_ticker` no longer waits; tickers are added unvalidated and stay unpriced (`NO_PRICE`). **No silent fallback to the simulator**: showing fake prices to someone who configured real data would mislead them. |
| 429 | Back off 60 s, then continue |
| 403 while in snapshot mode | Plan downgraded: re-detect the mode on the next poll |
| 5xx / timeout / network | Retry after `max(poll_interval, 5 s)` (snapshot) or 60 s (eod / detecting). Cached prices stay. |
| Malformed JSON / unexpected shape | Logged with a traceback, then retried as above. The task never dies (C7). |
| First poll not done when a ticker is added | `add_ticker` waits up to 10 s for it, then accepts the ticker unvalidated rather than block the user |
| Validation call fails (network) | Ticker accepted unvalidated; it gets priced on the next successful poll if it exists |

`stop()` cancels the task even while it's asleep inside `_throttle()`. `CancelledError` is a `BaseException` and isn't caught by `except Exception`.

---

## 9. Factory and environment variables

```python
# backend/app/market/factory.py
import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive import MassiveDataSource
from .simulator import SimulatorDataSource

log = logging.getLogger(__name__)

MIN_POLL_INTERVAL = 2.0


def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty -> Massive; otherwise the simulator (PLAN.md §5)."""
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if not api_key:
        log.info("Market data: built-in simulator")
        return SimulatorDataSource(cache)
    try:
        interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
    except ValueError:
        interval = 15.0
    interval = max(interval, MIN_POLL_INTERVAL)
    log.info("Market data: Massive API (snapshot poll every %.0fs on paid plans)", interval)
    return MassiveDataSource(cache, api_key=api_key, poll_interval=interval)
```

| Variable | Default | Meaning |
|---|---|---|
| `MASSIVE_API_KEY` | empty | Non-empty → Massive; empty or absent → simulator (`PLAN.md` §5) |
| `MASSIVE_POLL_INTERVAL` | `15` | Seconds between snapshot polls on paid plans (minimum 2). Ignored in eod mode. This is the "configurable interval" from `PLAN.md` §6. |

Add to `.env.example`:

```bash
# Optional: seconds between Massive snapshot polls on paid plans (default 15, min 2)
MASSIVE_POLL_INTERVAL=15
```

---

## 10. The priced set and route integration

### 10.1 `priced.py`

```python
# backend/app/market/priced.py
import sqlite3

from .interface import MarketDataSource


def load_priced_tickers(conn: sqlite3.Connection, user_id: str = "default") -> set[str]:
    """Watchlist ∪ open positions (PLAN.md §6 'Which Tickers Are Priced')."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? UNION SELECT ticker FROM positions WHERE user_id = ?",
        (user_id, user_id),
    ).fetchall()
    return {row[0] for row in rows}


async def sync_priced_tickers(conn: sqlite3.Connection, source: MarketDataSource, user_id: str = "default") -> None:
    await source.sync(load_priced_tickers(conn, user_id))
```

This is written against the standard-library `sqlite3` connection. If the backend's DB layer uses `aiosqlite` or a helper class, keep the same SQL and make `load_priced_tickers` async.

### 10.2 One lock for everything that changes the priced set

`PLAN.md` §7 already calls for one process-wide `asyncio.Lock` around trades. **Use the same lock for watchlist add/remove, reset and chat actions.** Without it there is a race. A trade calls `add_ticker("ORCL")` and then awaits. Meanwhile a watchlist removal runs `sync_priced_tickers`, which reads the database before the trade's position row exists, sees ORCL as neither watched nor held, and removes it. The trade then fails with `NO_PRICE`. With one user the lock costs nothing in practice.

Store it on `app.state.lock` (§12).

### 10.3 Where each route plugs in

| Operation (all under `app.state.lock`) | Market calls, in order |
|---|---|
| **Add to watchlist** | `t = normalize_ticker(raw)` → `await source.add_ticker(t)` (`UnknownTickerError` → 400, nothing written) → `INSERT OR IGNORE` row → return the entry built from `cache.get(t)` |
| **Remove from watchlist** | `normalize_ticker` → delete row (none deleted → 404 `NOT_FOUND`) → `await sync_priced_tickers(...)`: the ticker stays priced if it's still held |
| **Trade** | `normalize_ticker` → `await source.add_ticker(t)` (an unwatched, unheld ticker gets a price so it can fill) → `cache.get_price(t)`; `None` → `NO_PRICE` → execute trade (portfolio module) → **finally** `await sync_priced_tickers(...)`, which drops `t` again if the trade failed, or if it was fully sold and isn't watched |
| **Chat actions** | Same as the manual watchlist and trade paths, one action at a time; `MarketDataError` → action `status: "error"` |
| **Reset** | Reset the DB → `await sync_priced_tickers(...)`: back to the 10 defaults |
| **Startup** | `await source.start(load_priced_tickers(db))` in the lifespan hook |

Calling `add_ticker` before a trade is what makes `PLAN.md` §7's "Buying a ticker that isn't on the watchlist is allowed… the ticker becomes priced because it is now held" work. Without it, an unwatched ticker would never have a cached price and the buy could never fill.

### 10.4 Watchlist routes (reference implementation)

```python
# backend/app/routes/watchlist.py
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.market import EMPTY_PRICE_FIELDS, normalize_ticker, sync_priced_tickers

router = APIRouter()


def watch_entry(cache, ticker: str) -> dict:
    update = cache.get(ticker)
    return update.to_dict() if update else {"ticker": ticker, **EMPTY_PRICE_FIELDS}


@router.get("/api/watchlist")
async def get_watchlist(request: Request):
    db, cache = request.app.state.db, request.app.state.price_cache
    rows = db.execute("SELECT ticker FROM watchlist WHERE user_id='default' ORDER BY added_at, ticker").fetchall()
    return {"tickers": [watch_entry(cache, r[0]) for r in rows]}


@router.post("/api/watchlist")
async def add_to_watchlist(body: dict, request: Request):
    st = request.app.state
    ticker = normalize_ticker(body.get("ticker"))           # InvalidTickerError -> 400
    async with st.lock:
        await st.market.add_ticker(ticker)                  # UnknownTickerError -> 400, nothing written
        st.db.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, datetime.now(timezone.utc).isoformat()),
        )
        st.db.commit()
    return watch_entry(st.price_cache, ticker)


@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, request: Request):
    st = request.app.state
    ticker = normalize_ticker(ticker)
    async with st.lock:
        cur = st.db.execute("DELETE FROM watchlist WHERE user_id='default' AND ticker=?", (ticker,))
        st.db.commit()
        if cur.rowcount == 0:
            return JSONResponse({"error": f"{ticker} is not on the watchlist", "code": "NOT_FOUND"}, 404)
        await sync_priced_tickers(st.db, st.market)          # stays priced if still held
    return Response(status_code=204)
```

### 10.5 Trade route — the market-data part

The portfolio maths (cash, weighted average cost, rounding, snapshots) belongs to the portfolio module. This sketch shows only where market data comes in:

```python
# backend/app/routes/trade_sketch.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.market import normalize_ticker, sync_priced_tickers

router = APIRouter()


@router.post("/api/portfolio/trade")
async def trade(body: dict, request: Request):
    st = request.app.state
    ticker = normalize_ticker(body.get("ticker"))
    async with st.lock:                                       # PLAN.md §7: one process-wide lock
        try:
            await st.market.add_ticker(ticker)                # so an unwatched ticker gets a price
            price = st.price_cache.get_price(ticker)
            if price is None:
                return JSONResponse({"error": f"No price yet for {ticker}", "code": "NO_PRICE"}, 400)
            # ... execute_trade(db, ticker, side, quantity, price) — portfolio module, not market data ...
            return {"ticker": ticker, "price": price}
        finally:
            await sync_priced_tickers(st.db, st.market)       # drop it again if not watched/held
```

In the real route, `execute_trade` raises its own errors (`INVALID_QUANTITY`, `INSUFFICIENT_CASH`, …). The `finally` makes sure the priced set is correct whatever happens.

### 10.6 Reading prices elsewhere

```python
cache: PriceCache = request.app.state.price_cache

update = cache.get("AAPL")                 # PriceUpdate | None
price = cache.get_price("AAPL")            # float | None

# Portfolio valuation (PLAN.md §8: fall back to avg_cost when unpriced)
current_price = price if price is not None else position.avg_cost

# LLM context (PLAN.md §9 step 1): watchlist with live prices
watch_lines = [
    f"{t}: ${u.price:.2f} ({u.change_percent:+.2f}% today)" if (u := cache.get(t)) else f"{t}: no price yet"
    for t in watched
]
```

---

## 11. SSE endpoint

```python
# backend/app/market/stream.py
import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

TICK_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0

stream_router = APIRouter()


async def price_events(cache: PriceCache, request: Request) -> AsyncIterator[str]:
    """SSE frames per PLAN.md §6: every ticker on connect, then only changed tickers; empty ticks skipped."""
    yield "retry: 1000\n\n"  # EventSource reconnect delay (ms)
    sent: dict[str, datetime] = {}  # ticker -> timestamp last sent to this client
    first = True
    seen_version = -1
    last_frame = time.monotonic()

    while not await request.is_disconnected():
        if cache.version != seen_version:
            seen_version = cache.version
            snap = cache.snapshot()
            for gone in sent.keys() - snap.keys():
                del sent[gone]  # so a re-added ticker is sent again
            changed = {t: u for t, u in snap.items() if first or sent.get(t) != u.timestamp}
            if changed:
                sent.update({t: u.timestamp for t, u in changed.items()})
                first = False
                last_frame = time.monotonic()
                payload = {t: u.to_dict() for t, u in changed.items()}
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"

        if time.monotonic() - last_frame >= KEEPALIVE_SECONDS:
            last_frame = time.monotonic()
            yield ": keepalive\n\n"  # comment frame; stops proxies closing a quiet Massive stream

        await asyncio.sleep(TICK_SECONDS)


@stream_router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    return StreamingResponse(
        price_events(request.app.state.price_cache, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

How the frames meet `PLAN.md` §6:

| Requirement | Implementation |
|---|---|
| One unnamed `data:` event per ~500 ms tick, JSON keyed by ticker | `data: {"AAPL": {...}, ...}\n\n` with no `event:` line, so `EventSource.onmessage` gets it |
| First event contains every priced ticker | `first` stays `True` until a non-empty frame is sent, so a client that connects before Massive's first poll still gets the full set |
| Later events contain only tickers whose `timestamp` changed | `sent` records the timestamp last sent to *this* client |
| Empty ticks are skipped | No `data:` frame when `changed` is empty; `cache.version` lets the loop skip the snapshot entirely |
| Reconnection | `retry: 1000` sets EventSource's retry to 1 s; a reconnect is a new connection, so it gets a full first frame |

Extras: a `: keepalive` comment every 15 s of silence (needed with Massive, where minutes can pass without a change) keeps proxies from closing the stream. `X-Accel-Buffering: no` stops nginx-style proxies from buffering. Removed tickers just stop appearing; the frontend drops them when it refetches `GET /api/watchlist`.

Example stream (simulator, from the running prototype; abbreviated):

```
retry: 1000

data: {"AAPL":{"ticker":"AAPL","price":189.93,"previous_price":189.91,"open_price":190.0,"change_percent":-0.04,"direction":"up","timestamp":"2026-10-12T20:21:53.012Z"},"GOOGL":{...},...}

data: {"AAPL":{"ticker":"AAPL","price":189.97,"previous_price":189.93,"open_price":190.0,"change_percent":-0.02,"direction":"up","timestamp":"2026-10-12T20:21:53.512Z"},...}
```

Frontend side (for reference; the frontend owns this):

```ts
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const updates: Record<string, PriceUpdate> = JSON.parse(e.data);
  for (const u of Object.values(updates)) priceStore.push(u.ticker, u);   // sparkline + main chart history
};
// status dot: es.readyState → 0 CONNECTING = yellow, 1 OPEN = green, 2 CLOSED = red
```

---

## 12. App wiring

The market-data part of `app/main.py`. `init_db` here is a stand-in; use the real database module.

```python
# backend/app/main.py
import asyncio
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.market import MarketDataError, PriceCache, create_market_data_source, load_priced_tickers, stream_router
from app.routes import trade_sketch, watchlist


def init_db() -> sqlite3.Connection:  # stand-in for app.database.init_db
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.executescript("""
      CREATE TABLE watchlist (id TEXT PRIMARY KEY, user_id TEXT DEFAULT 'default', ticker TEXT, added_at TEXT,
                              UNIQUE(user_id, ticker));
      CREATE TABLE positions (id TEXT PRIMARY KEY, user_id TEXT DEFAULT 'default', ticker TEXT, quantity REAL,
                              avg_cost REAL, updated_at TEXT, UNIQUE(user_id, ticker));
    """)
    for i, t in enumerate(["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]):
        db.execute("INSERT INTO watchlist VALUES (?, 'default', ?, ?)", (str(i), t, f"2026-01-01T00:00:{i:02d}"))
    db.commit()
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = init_db()
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(load_priced_tickers(db))
    app.state.db, app.state.price_cache, app.state.market = db, cache, source
    app.state.lock = asyncio.Lock()
    try:
        yield
    finally:
        await source.stop()
        db.close()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(MarketDataError)
async def market_error_handler(request: Request, exc: MarketDataError):
    return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.http_status)


app.include_router(stream_router)
app.include_router(watchlist.router)
app.include_router(trade_sketch.router)
```

In the real `main.py`:

- After `source.start(...)`, the lifespan also starts the 30 s portfolio snapshot task (`PLAN.md` §7), which reads `cache` for valuations, and cancels it before `source.stop()`.
- The `StaticFiles` mount goes **last**: `app.mount("/", StaticFiles(directory="static", html=True), name="static")` (`PLAN.md` §11).
- `GET /api/health` stays `{"status": "ok"}`. `source.name` is logged at startup (`massive:snapshot` / `massive:eod` / `simulator`) for diagnosis.

---

## 13. Usage examples

### 13.1 Watch prices in a terminal — `demo.py`

```python
# backend/app/market/demo.py
"""Watch live prices in the terminal:  cd backend && uv run python -m app.market.demo"""
import asyncio
import logging

from . import PriceCache, create_market_data_source
from .seed_data import DEFAULT_TICKERS


async def main(seconds: float = 10.0) -> None:
    logging.basicConfig(level=logging.INFO)
    cache = PriceCache()
    source = create_market_data_source(cache)  # simulator unless MASSIVE_API_KEY is set
    await source.start(DEFAULT_TICKERS)
    try:
        for _ in range(int(seconds * 2)):
            await asyncio.sleep(0.5)
            print("  ".join(
                f"{u.ticker:<5}{u.price:>8.2f} {u.change_percent:+5.2f}%{'▲' if u.direction == 'up' else '▼' if u.direction == 'down' else ' '}"
                for u in list(cache.snapshot().values())[:5]
            ))
    finally:
        await source.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

```
$ cd backend && uv run python -m app.market.demo
INFO:app.market.factory:Market data: built-in simulator
AAPL   190.00 +0.00%   GOOGL  175.00 +0.00%   MSFT   420.00 +0.00%   AMZN   185.00 +0.00%   TSLA   250.00 +0.00%
AAPL   189.90 -0.05%▼  GOOGL  174.93 -0.04%▼  MSFT   419.83 -0.04%▼  AMZN   185.01 +0.01%▼  TSLA   249.86 -0.06%▼
AAPL   189.87 -0.07%▼  GOOGL  174.89 -0.06%▼  MSFT   419.77 -0.05%▼  AMZN   184.97 -0.02%▼  TSLA   249.90 -0.04%▲
```

(Notice AMZN: `+0.01%` since the open but `▼` since the last tick. `change_percent` and `direction` measure different things.)

With `MASSIVE_API_KEY=... uv run python -m app.market.demo` the same script shows real prices and logs the detected mode.

### 13.2 Using the pieces directly

```python
import asyncio, random
from app.market import GBMSimulator, PriceCache, SimulatorDataSource

# Deterministic simulator, no event loop needed
sim = GBMSimulator(rng=random.Random(42))
sim.add("AAPL"); sim.add("PYPL")          # PYPL: random seed in [$50, $300]
for _ in range(3):
    print(sim.step())                     # {'AAPL': <new price>, 'PYPL': <new price>}

# Async source writing to a cache
async def main():
    cache = PriceCache()
    src = SimulatorDataSource(cache)
    await src.start(["AAPL", "MSFT"])
    print(cache.get("AAPL").to_dict())    # priced immediately, open_price == seed
    await asyncio.sleep(1.1)
    print(cache.get("AAPL").direction)    # 'up' / 'down' / 'flat'
    await src.stop()

asyncio.run(main())
```

### 13.3 API responses that come from the cache

```bash
$ curl -s localhost:8000/api/watchlist | jq '.tickers[0]'
{"ticker":"AAPL","price":190.12,"previous_price":190.05,"open_price":189.5,"change_percent":0.33,"direction":"up","timestamp":"2026-10-12T14:03:21.512Z"}

$ curl -s -XPOST localhost:8000/api/watchlist -d '{"ticker":"pypl"}' -H 'content-type: application/json'
{"ticker":"PYPL","price":143.27,"previous_price":143.27,"open_price":143.27,"change_percent":0.0,"direction":"flat","timestamp":"…"}

$ curl -s -XPOST localhost:8000/api/watchlist -d '{"ticker":"AB1"}' -H 'content-type: application/json'
{"error":"Invalid ticker: 'AB1'","code":"INVALID_TICKER"}

# Massive mode only:
$ curl -s -XPOST localhost:8000/api/watchlist -d '{"ticker":"ZZZZ"}' -H 'content-type: application/json'
{"error":"Unknown ticker: ZZZZ","code":"UNKNOWN_TICKER"}
```

---

## 14. Tests

All tests below pass (`54 passed`). In the backend they live in `backend/tests/market/`. Adjust the `tests.fake_massive` imports to `tests.market.fake_massive`.

### 14.1 Fake Massive server — `fake_massive.py`

Tests never touch the network. `MassiveDataSource` accepts an injected `httpx.AsyncClient` with a `MockTransport`:

```python
# backend/tests/market/fake_massive.py
"""In-memory stand-in for the Massive REST API, served through httpx.MockTransport."""
from __future__ import annotations

import httpx

from app.market.massive import BASE_URL


class FakeMassive:
    def __init__(self, *, plan: str = "paid") -> None:
        self.plan = plan  # "paid" -> snapshots allowed, "free" -> snapshot 403
        self.snapshot: dict[str, dict] = {}       # ticker -> snapshot item
        self.grouped: dict[str, list[dict]] = {}  # "YYYY-MM-DD" -> grouped-daily results
        self.calls: list[str] = []
        self.status_override: int | None = None

    def set_quote(self, ticker: str, price: float, prev_close: float, updated: int) -> None:
        self.snapshot[ticker] = {
            "ticker": ticker,
            "updated": updated,
            "day": {"o": prev_close, "c": price},
            "prevDay": {"c": prev_close},
            "min": {"c": price, "t": updated // 1_000_000},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if self.status_override:
            return httpx.Response(self.status_override, json={"status": "ERROR"})
        path = request.url.path
        if path == "/v2/snapshot/locale/us/markets/stocks/tickers":
            if self.plan == "free":
                return httpx.Response(403, json={"status": "NOT_AUTHORIZED"})
            wanted = request.url.params["tickers"].split(",")
            items = [self.snapshot[t] for t in wanted if t in self.snapshot]
            return httpx.Response(200, json={"status": "OK", "count": len(items), "tickers": items})
        if path.startswith("/v2/aggs/grouped/locale/us/market/stocks/"):
            day = path.rsplit("/", 1)[1]
            results = self.grouped.get(day, [])
            return httpx.Response(200, json={"status": "OK", "resultsCount": len(results), "results": results})
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(self.handler))
```

### 14.2 Shared contract suite — `test_contract.py`

One parametrized module runs against the simulator, Massive snapshot mode and Massive eod mode:

```python
# backend/tests/market/test_contract.py
"""Shared contract suite: every MarketDataSource must pass (C1-C6)."""
import asyncio
from datetime import datetime

import pytest

from app.market import MassiveDataSource, PriceCache, SimulatorDataSource
from app.market import massive as m
from tests.fake_massive import FakeMassive
from tests.test_massive import grouped, until


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
```

### 14.3 Massive — `test_massive.py`

```python
# backend/tests/market/test_massive.py
import asyncio
from datetime import date, datetime

import pytest

from app.market import MassiveDataSource, PriceCache, UnknownTickerError
from app.market import massive as m
from tests.fake_massive import FakeMassive

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
```

### 14.4 Simulator — `test_simulator.py`

Statistical tests use a fixed seed, so they are deterministic and not flaky:

```python
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
```

### 14.5 Cache, models, tickers — `test_cache_and_tickers.py`

```python
# backend/tests/market/test_cache_and_tickers.py
from datetime import datetime, timezone

import pytest

from app.market import InvalidTickerError, PriceCache, PriceUpdate, normalize_ticker


def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    u = cache.update("AAPL", 190.123)
    assert (u.price, u.previous_price, u.open_price) == (190.12, 190.12, 190.12)
    assert u.direction == "flat" and u.change_percent == 0.0


def test_later_updates_keep_open_price_and_track_previous():
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    u = cache.update("AAPL", 101.0)
    assert (u.previous_price, u.open_price, u.direction, u.change_percent) == (100.0, 100.0, "up", 1.0)
    u = cache.update("AAPL", 99.0, open_price=98.0)  # explicit open (Massive prev close)
    assert (u.open_price, u.direction) == (98.0, "down")


def test_version_bumps_and_remove():
    cache = PriceCache()
    v0 = cache.version
    cache.update("AAPL", 1.0)
    assert cache.version == v0 + 1
    cache.remove("AAPL")
    cache.remove("AAPL")  # no-op
    assert cache.version == v0 + 2 and "AAPL" not in cache and cache.get_price("AAPL") is None


def test_to_dict_shape():
    ts = datetime(2026, 10, 12, 14, 3, 21, 512000, tzinfo=timezone.utc)
    d = PriceUpdate("AAPL", 190.12, 190.05, 189.50, ts).to_dict()
    assert d == {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "open_price": 189.5,
                 "change_percent": 0.33, "direction": "up", "timestamp": "2026-10-12T14:03:21.512Z"}


def test_zero_open_price():
    assert PriceUpdate("X", 1.0, 1.0, 0.0, datetime.now(timezone.utc)).change_percent == 0.0


@pytest.mark.parametrize("raw,expected", [(" aapl ", "AAPL"), ("brk.b", "BRK.B"), ("V", "V")])
def test_normalize_ok(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "TOOLONG", "AB1", "BRK-B", None, 123])
def test_normalize_rejects(raw):
    with pytest.raises(InvalidTickerError) as e:
        normalize_ticker(raw)
    assert e.value.code == "INVALID_TICKER"
```

### 14.6 SSE framing — `test_stream.py`

`price_events` is tested directly with a fake `Request` and a patched `asyncio.sleep`, so there is no real waiting:

```python
# backend/tests/market/test_stream.py
import json

from app.market import PriceCache
from app.market import stream as s


class FakeRequest:
    def __init__(self, frames_before_disconnect: int):
        self.left = frames_before_disconnect

    async def is_disconnected(self):
        self.left -= 1
        return self.left < 0


async def collect(cache, ticks, monkeypatch, between=None):
    async def fake_sleep(_):
        if between:
            between.pop(0)() if between else None
    monkeypatch.setattr(s.asyncio, "sleep", fake_sleep)
    return [f async for f in s.price_events(cache, FakeRequest(ticks))]


def data_frames(frames):
    return [json.loads(f[6:]) for f in frames if f.startswith("data: ")]


async def test_first_frame_full_then_only_changes(monkeypatch):
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    steps = [lambda: cache.update("AAPL", 191.0), lambda: None, lambda: cache.update("MSFT", 421.0)]
    frames = await collect(cache, 4, monkeypatch, steps)
    assert frames[0] == "retry: 1000\n\n"
    data = data_frames(frames)
    assert [set(d) for d in data] == [{"AAPL", "MSFT"}, {"AAPL"}, {"MSFT"}]   # empty tick skipped
    assert data[1]["AAPL"]["direction"] == "up"


async def test_empty_cache_waits_for_full_first_frame(monkeypatch):
    cache = PriceCache()
    steps = [lambda: None, lambda: (cache.update("AAPL", 1.0), cache.update("MSFT", 2.0))]
    data = data_frames(await collect(cache, 3, monkeypatch, steps))
    assert [set(d) for d in data] == [{"AAPL", "MSFT"}]


async def test_keepalive(monkeypatch):
    cache = PriceCache()
    clock = [0.0]
    monkeypatch.setattr(s.time, "monotonic", lambda: clock[0])
    steps = [lambda: clock.__setitem__(0, 16.0)]
    frames = await collect(cache, 2, monkeypatch, steps)
    assert ": keepalive\n\n" in frames
```

### 14.7 Route wiring smoke test

```python
# backend/tests/market/test_app.py
from fastapi.testclient import TestClient

from app.main import app


def test_routes(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(app) as c:
        wl = c.get("/api/watchlist").json()["tickers"]
        assert len(wl) == 10 and wl[0]["ticker"] == "AAPL" and wl[0]["price"] == 190.0
        r = c.post("/api/watchlist", json={"ticker": " pypl "})
        assert r.status_code == 200 and r.json()["ticker"] == "PYPL" and r.json()["price"] is not None
        assert c.post("/api/watchlist", json={"ticker": "pypl"}).status_code == 200      # idempotent
        r = c.post("/api/watchlist", json={"ticker": "BAD1"})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_TICKER"
        assert c.delete("/api/watchlist/PYPL").status_code == 204
        assert "PYPL" not in app.state.market.tickers and "PYPL" not in app.state.price_cache
        assert c.delete("/api/watchlist/PYPL").json()["code"] == "NOT_FOUND"
        r = c.post("/api/portfolio/trade", json={"ticker": "ORCL", "quantity": 1, "side": "buy"})
        assert r.status_code == 200 and r.json()["price"] > 0
        assert "ORCL" not in app.state.market.tickers   # not held in this sketch -> dropped again
```

### 14.8 Coverage against `PLAN.md` §12

| `PLAN.md` §12 requirement | Tests |
|---|---|
| Simulator generates valid prices | `test_seed_prices`, `test_prices_stay_positive_under_extreme_vol`, `test_adapter_lifecycle` |
| GBM maths is correct | `test_gbm_moments`, `test_correlation_structure`, `test_events_move_2_to_5_percent`, `test_no_events_small_moves` |
| Unknown tickers get a seed price | `test_seed_prices` (PYPL in [50, 300]) |
| Massive response parsing works | `test_pick_price_order_and_zero_skipping`, `test_snapshot_prices_and_open`, `test_eod_detects_and_prices`, `test_reset_window_does_not_jump_to_prev_close` |
| Both implementations meet the interface | `test_contract.py` × 3 variants |
| API routes: status codes, error codes | `test_routes`, plus the backend's own route tests |

---

## 15. Departures from `PLAN.md` and changes from `MARKET_INTERFACE.md`

### Departures from `PLAN.md` (PLAN.md should be updated to match)

1. **The free Massive tier is end-of-day only.** `PLAN.md` §6 says "Free tier (5 calls/min): poll every 15 seconds". The free plan has no snapshot access (403), so this design detects the plan and uses grouped-daily closes on free keys. Suggested wording for §6: *"Free tier: end-of-day closes only (prices update once per trading day). Paid tiers: snapshot polling every `MASSIVE_POLL_INTERVAL` seconds (default 15)."*
2. **New env var `MASSIVE_POLL_INTERVAL`** (default 15 s, minimum 2) for the "configurable interval".
3. **Trades call `add_ticker` before reading the price**, so buying an unwatched ticker can fill (§10.3).
4. **The trade lock also guards watchlist changes, reset and chat actions** (§10.2).
5. **A bad Massive key doesn't fall back to the simulator.** The app runs; prices don't stream; one clear error is logged.

### Changes from the code in `MARKET_INTERFACE.md`

| Area | Change | Why |
|---|---|---|
| Dependencies | numpy removed | The simulator only uses the standard library (`MARKET_SIMULATOR.md` already said so) |
| Errors | `MarketDataError` base with `code` / `http_status` | One exception handler, and the chat executor can record `code` |
| `normalize_ticker` | Non-string input → `INVALID_TICKER` | JSON bodies can carry `null` or numbers |
| Massive price fallback | `prevDay.c` only for a ticker's first price | Avoids a jump back to yesterday's close during the 3:30–4:00 AM ET data reset |
| Massive throttle | Applies to *every* call while the mode is eod or still being detected, and is serialized with a lock | The detection call counts toward the 5/min budget; concurrent callers could otherwise exceed it |
| Massive eod | Weekends skipped without calls; today's bars aren't looked for before 16:15 ET | Free-tier calls drop from ~5 per refresh to ~1 per trading day |
| Massive 401 | Sets `_dead`; `add_ticker` stops waiting 10 s | Each watchlist add would otherwise hang for 10 s with a bad key |
| Massive 403 later | Re-detects the mode | Handles a plan downgrade without a restart |
| Massive validation | Network failure during `add_ticker` → accept unvalidated | A transient error shouldn't block the user |
| Massive `stop()` | Idempotent; only closes a client it created | C6; injected test clients are closed by the test |
| Simulator loop | Resyncs after falling behind | No burst of catch-up ticks after the host sleeps |
| `start()` | Idempotent (no second task) | Defensive |
| Priced set | `load_priced_tickers` is one `UNION` query on `sqlite3` | Concrete instead of a placeholder DB helper |
| Seed data | Extra profiles (AMD, INTC, BAC, GS, DIS); TSLA has no sector; `DEFAULT_TICKERS` exported | More realistic additions; one source for the default list |
| Cache | `clear()` removed | Nothing used it; reset goes through `sync()` |

---

## 16. Implementation checklist

In order. Each step is testable on its own.

1. `backend/pyproject.toml` with the dependencies in §2; `uv sync`.
2. `models.py`, `cache.py`, `tickers.py` → run `test_cache_and_tickers.py`.
3. `interface.py`, `seed_data.py`, `simulator.py` → run `test_simulator.py`.
4. `massive.py` + `tests/market/fake_massive.py` → run `test_massive.py`.
5. `factory.py`, `priced.py`, `__init__.py` → run `test_contract.py`.
6. `stream.py` → run `test_stream.py`; then `uv run uvicorn app.main:app` and `curl -N localhost:8000/api/stream/prices`.
7. Wire the lifespan, `app.state.lock` and the exception handler into `main.py` (§12); use `normalize_ticker` / `add_ticker` / `sync_priced_tickers` in the watchlist, trade, chat and reset routes exactly as §10.3 says.
8. Add `MASSIVE_POLL_INTERVAL` to `.env.example`; update `PLAN.md` §6 per §15.
9. `uv run python -m app.market.demo` to check by eye; with a real `MASSIVE_API_KEY`, check that the log shows the expected mode.
