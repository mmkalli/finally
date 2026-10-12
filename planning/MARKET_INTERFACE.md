# Market Data Interface — Design

The unified Python API that the FinAlly backend uses to get stock prices. One interface, two implementations:

- **`SimulatorDataSource`** — default; in-process GBM simulator (details in `MARKET_SIMULATOR.md`)
- **`MassiveDataSource`** — used when `MASSIVE_API_KEY` is set; polls the Massive REST API (details in `MASSIVE_API.md`)

Nothing downstream (SSE, portfolio valuation, trade execution, LLM context) knows which one is running. It all reads from one in-memory **`PriceCache`**.

This document implements `PLAN.md` §6 (Market Data) and the market-related parts of §7–§8. Where it refines or departs from `PLAN.md`, §11 says so.

---

## 1. Shape of the system

```
                    ┌───────────────────────────── backend process ─────────────────────────────┐
                    │                                                                           │
  MASSIVE_API_KEY?  │   create_market_data_source(cache)                                        │
        │           │        │                                                                  │
        ├── no ───────────▶  SimulatorDataSource ──┐   (500 ms tick, writes every ticker)       │
        │           │                              ├──▶  PriceCache  ◀── read ── SSE /api/stream/prices
        └── yes ──────────▶  MassiveDataSource ────┘   (poll, writes      ◀── read ── portfolio valuation
                    │                                   changed tickers)  ◀── read ── trade execution (fill price)
                    │                                                     ◀── read ── LLM portfolio context
                    │                                                                           │
                    │   watchlist / trade / reset routes ── sync_priced_tickers() ──▶ source    │
                    └───────────────────────────────────────────────────────────────────────────┘
```

Rules:

1. **Exactly one writer.** Only the active data source writes to the `PriceCache`. Everything else reads.
2. **The source owns the set of priced tickers**, but it doesn't decide that set. The routes tell it, via `sync_priced_tickers()`, to track *watchlist ∪ open positions* (`PLAN.md` §6).
3. **Everything runs on the asyncio event loop.** Both sources are async, and the cache has no `await` points, so it needs no locks.
4. **Nobody waits for a price.** A ticker without a cached price is reported as `NO_PRICE` (trades) or `null` fields (watchlist). Sources do try to price a ticker at the moment it's added, so the gap is usually zero.

---

## 2. Module layout

```
backend/app/market/
├── __init__.py          # re-exports the public API below
├── models.py            # PriceUpdate
├── cache.py             # PriceCache
├── tickers.py           # normalize_ticker(), InvalidTickerError, UnknownTickerError
├── interface.py         # MarketDataSource (ABC)
├── factory.py           # create_market_data_source()
├── simulator.py         # GBMSimulator (pure math) + SimulatorDataSource (async adapter)
├── seed_data.py         # seed prices, per-ticker drift/vol, sectors
├── massive.py           # MassiveDataSource
├── priced.py            # sync_priced_tickers() — watchlist ∪ positions
└── stream.py            # SSE router: GET /api/stream/prices
```

Public API (`from app.market import ...`):

```python
PriceUpdate, PriceCache,
MarketDataSource, create_market_data_source,
normalize_ticker, InvalidTickerError, UnknownTickerError,
sync_priced_tickers, stream_router
```

Dependencies: `numpy` (simulator), `httpx` (Massive; already pulled in by FastAPI tooling / LiteLLM, but list it explicitly in `pyproject.toml`).

---

## 3. `PriceUpdate` — the one price record

```python
# backend/app/market/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Direction = Literal["up", "down", "flat"]


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable price record for one ticker. Matches the SSE / watchlist JSON shape (PLAN.md §6, §8)."""

    ticker: str
    price: float
    previous_price: float
    open_price: float
    timestamp: datetime  # timezone-aware, UTC

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
            "timestamp": self.timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
```

`change_percent` and `direction` are worked out from the stored fields, so they can never disagree with them.

---

## 4. `PriceCache`

```python
# backend/app/market/cache.py
from __future__ import annotations

from datetime import datetime, timezone

from .models import PriceUpdate


class PriceCache:
    """In-memory latest price per ticker. Single writer (the active MarketDataSource), many readers.

    All access happens on the event loop and no method awaits, so no lock is needed.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._version = 0  # bumped on every write; lets readers skip work when nothing changed

    # ---- writes (data source only) ----

    def update(
        self,
        ticker: str,
        price: float,
        *,
        timestamp: datetime | None = None,
        open_price: float | None = None,
    ) -> PriceUpdate:
        """Record a new price.

        previous_price := the price before this update (or this price, on first sight).
        open_price     := the explicit value if given (Massive: previous close),
                          else the existing open_price, else this price (simulator: first price this session).
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

    def clear(self) -> None:
        self._prices.clear()
        self._version += 1

    # ---- reads ----

    def get(self, ticker: str) -> PriceUpdate | None:
        return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        update = self._prices.get(ticker)
        return update.price if update else None

    def snapshot(self) -> dict[str, PriceUpdate]:
        """A shallow copy; safe to iterate while the source keeps writing."""
        return dict(self._prices)

    @property
    def version(self) -> int:
        return self._version

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._prices

    def __len__(self) -> int:
        return len(self._prices)
```

---

## 5. Tickers and errors

```python
# backend/app/market/tickers.py
import re

TICKER_RE = re.compile(r"^[A-Z.]{1,6}$")


class InvalidTickerError(ValueError):
    """Ticker fails format validation → API code INVALID_TICKER (400)."""


class UnknownTickerError(ValueError):
    """Data source has no data for the ticker → API code UNKNOWN_TICKER (400). Massive only."""


def normalize_ticker(raw: str) -> str:
    """Uppercase + trim, then validate format (PLAN.md §6 'Ticker Validation')."""
    ticker = (raw or "").strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise InvalidTickerError(f"Invalid ticker: {raw!r}")
    return ticker
```

Every entry point (watchlist route, trade route, chat action executor) calls `normalize_ticker()` first. Data sources only ever see normalized tickers.

---

## 6. `MarketDataSource` — the abstract interface

```python
# backend/app/market/interface.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .cache import PriceCache
from .tickers import UnknownTickerError


class MarketDataSource(ABC):
    """Produces prices for a dynamic set of tickers and writes them into a PriceCache.

    Lifecycle: start() once in the FastAPI lifespan → add/remove tickers at runtime → stop() on shutdown.
    All methods take normalized tickers (see normalize_ticker).
    """

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Begin producing prices for `tickers` in a background task. Must return quickly (no long network waits)."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel background work and release resources. Idempotent."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start pricing `ticker`. Idempotent.

        Should put a first price into the cache before returning when it can do so cheaply
        (simulator: always; Massive: from the validation call).
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
        """For logs and /api/health diagnostics, e.g. 'simulator' or 'massive:snapshot'."""
        return type(self).__name__

    async def sync(self, desired: Iterable[str]) -> None:
        """Make the priced set equal to `desired` (adds first, so a failed add leaves nothing half-removed)."""
        desired = set(desired)
        current = self.tickers
        for ticker in sorted(desired - current):
            try:
                await self.add_ticker(ticker)
            except UnknownTickerError:
                pass  # can't price it; sync is best-effort, callers validate on the user-facing path
        for ticker in sorted(current - desired):
            await self.remove_ticker(ticker)
```

### Contract every implementation must meet (enforced by a shared test suite, §12)

| # | Behaviour |
|---|---|
| C1 | After `start(T)`, every ticker in `T` gets a cache entry within one update interval (simulator: right away). |
| C2 | `add_ticker(t)` is idempotent; after it returns, `t in source.tickers`. |
| C3 | `remove_ticker(t)` removes `t` from `source.tickers` **and** from the cache; later updates never bring it back. |
| C4 | Cache writes only happen for tickers in `source.tickers`. |
| C5 | A ticker's `timestamp` only changes when its price data actually changed (Massive) or a tick happened (simulator). |
| C6 | `stop()` is idempotent and leaves no running tasks. |
| C7 | A network or API failure never crashes the background task. The last known prices stay in the cache. |

---

## 7. Factory and environment

```python
# backend/app/market/factory.py
import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive import MassiveDataSource
from .simulator import SimulatorDataSource

log = logging.getLogger(__name__)


def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if api_key:
        interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
        log.info("Market data: Massive API (poll every %.0fs)", interval)
        return MassiveDataSource(cache, api_key=api_key, poll_interval=interval)
    log.info("Market data: built-in simulator")
    return SimulatorDataSource(cache)
```

| Variable | Default | Meaning |
|---|---|---|
| `MASSIVE_API_KEY` | empty | Non-empty → Massive; empty/absent → simulator |
| `MASSIVE_POLL_INTERVAL` | `15` | Seconds between snapshot polls (paid plans). Use 2–5 on Starter+ for livelier updates |

`MASSIVE_POLL_INTERVAL` is new. It's the "configurable interval" that `PLAN.md` §6 mentions. Add it to `.env.example`.

---

## 8. `MassiveDataSource`

Built on the findings in `MASSIVE_API.md`. Key points:

- It talks to the API with **`httpx.AsyncClient`**, not the official sync client (reasons in `MASSIVE_API.md` §6).
- It **detects the plan on its first poll**:
  - **Snapshot mode** (Starter+, snapshot returns 200): one `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=…` every `poll_interval`.
  - **EOD mode** (free Basic, snapshot returns 403): `GET /v2/aggs/grouped/locale/us/market/stocks/{date}` for the two latest trading days. That gives every US close in two calls. It refreshes every 5 minutes, but only spends a call when a new trading day might have closed. Calls are throttled to ≤ 5 per rolling minute.
- **Price:** `lastTrade.p` → `min.c` → `day.c` → `prevDay.c` (skipping missing/zero). **`open_price`** = `prevDay.c` (snapshot) or prior day's close (EOD).
- **Change detection:** a ticker is written to the cache only when its `updated` value (snapshot) or trading date (EOD) changed. With Massive, most SSE ticks are therefore empty, as `PLAN.md` §6 expects.
- **Validation (`UNKNOWN_TICKER`):** snapshot mode makes one snapshot call for that ticker; if it's missing from the response, the ticker is unknown. EOD mode looks the ticker up in the cached grouped-daily data at no API cost.
- `start()` returns right away. The first poll happens in the background task. `add_ticker()` waits up to 10 s for that first poll, so it knows the mode and has data to validate against.

```python
# backend/app/market/massive.py
from __future__ import annotations

import asyncio
import collections
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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

Mode = Literal["snapshot", "eod"]


@dataclass
class _EodData:
    day: date                       # most recent trading day with data
    closes: dict[str, float]        # ticker -> close on `day`
    prior_closes: dict[str, float]  # ticker -> close on the trading day before
    timestamp: datetime             # when `day`'s bars ended (UTC)


def _positive(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and x > 0 else None


def _pick_price(item: dict) -> float | None:
    return (
        _positive((item.get("lastTrade") or {}).get("p"))
        or _positive((item.get("min") or {}).get("c"))
        or _positive((item.get("day") or {}).get("c"))
        or _positive((item.get("prevDay") or {}).get("c"))
    )


def _ns_to_dt(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


class MassiveDataSource(MarketDataSource):
    EOD_REFRESH_SECONDS = 300.0
    FREE_TIER_CALLS_PER_MINUTE = 5
    SNAPSHOT_CHUNK = 100  # tickers per request, keeps URLs short

    def __init__(
        self,
        cache: PriceCache,
        *,
        api_key: str,
        poll_interval: float = 15.0,
        client: httpx.AsyncClient | None = None,  # injectable for tests (httpx.MockTransport)
    ) -> None:
        super().__init__(cache)
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        self._poll_interval = poll_interval
        self._tickers: set[str] = set()
        self._mode: Mode | None = None
        self._last_seen: dict[str, object] = {}  # ticker -> `updated` (snapshot) or trading date (EOD)
        self._eod: _EodData | None = None
        self._ready = asyncio.Event()             # set after the first successful poll
        self._call_times: collections.deque[float] = collections.deque()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ interface

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._tickers)

    @property
    def name(self) -> str:
        return f"massive:{self._mode or 'detecting'}"

    async def start(self, tickers: Iterable[str]) -> None:
        self._tickers = set(tickers)
        self._task = asyncio.create_task(self._run(), name="massive-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.aclose()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=10)
        except TimeoutError:
            # No data yet (API slow/unreachable). Accept unvalidated rather than block the user.
            log.warning("Massive not ready; adding %s without validation", ticker)
            self._tickers.add(ticker)
            return

        if self._mode == "snapshot":
            items = await self._fetch_snapshot([ticker])
            item = next((i for i in items if i.get("ticker") == ticker), None)
            if item is None:
                raise UnknownTickerError(f"Unknown ticker: {ticker}")
            self._tickers.add(ticker)
            self._apply_snapshot(item)
        else:  # eod
            if self._eod is None or ticker not in self._eod.closes:
                raise UnknownTickerError(f"Unknown ticker: {ticker}")
            self._tickers.add(ticker)
            self._apply_eod(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._last_seen.pop(ticker, None)
        self._cache.remove(ticker)

    # ------------------------------------------------------------------ loop

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
                    log.error("MASSIVE_API_KEY was rejected (401). Prices will not update. "
                              "Fix the key, or unset it to use the simulator.")
                    return
                log.warning("Massive poll failed with HTTP %s; retrying", status)
                delay = 60.0 if status == 429 else max(self._poll_interval, 5.0)
            except httpx.HTTPError as e:
                log.warning("Massive poll failed: %r; retrying", e)
                delay = max(self._poll_interval, 5.0)
            except Exception:  # never let the poller die (contract C7)
                log.exception("Unexpected error in Massive poller")
                delay = max(self._poll_interval, 5.0)

    async def _poll_once(self) -> None:
        if self._mode is None:
            self._mode = await self._detect_mode()
            log.info("Massive plan detected: %s mode", self._mode)
        if self._mode == "snapshot":
            await self._poll_snapshot()
        else:
            await self._poll_eod()

    async def _detect_mode(self) -> Mode:
        probe = next(iter(sorted(self._tickers)), "AAPL")
        resp = await self._get(SNAPSHOT_PATH, params={"tickers": probe}, raise_for_status=False)
        if resp.status_code == 403:
            return "eod"
        resp.raise_for_status()  # 401 / 429 / 5xx propagate to _run
        return "snapshot"

    # ------------------------------------------------------------------ snapshot mode

    async def _poll_snapshot(self) -> None:
        if not self._tickers:
            return
        for item in await self._fetch_snapshot(sorted(self._tickers)):
            self._apply_snapshot(item)

    async def _fetch_snapshot(self, tickers: list[str]) -> list[dict]:
        items: list[dict] = []
        for i in range(0, len(tickers), self.SNAPSHOT_CHUNK):
            chunk = tickers[i : i + self.SNAPSHOT_CHUNK]
            resp = await self._get(SNAPSHOT_PATH, params={"tickers": ",".join(chunk)})
            items.extend(resp.json().get("tickers") or [])
        return items

    def _apply_snapshot(self, item: dict) -> None:
        ticker = item.get("ticker")
        if ticker not in self._tickers:  # removed while the request was in flight (C3/C4)
            return
        updated = item.get("updated")
        if updated is None or self._last_seen.get(ticker) == updated:
            return
        price = _pick_price(item)
        if price is None:  # e.g. 3:30–4:00 AM ET when snapshot data is reset to zeros
            return
        self._cache.update(
            ticker,
            price,
            timestamp=_ns_to_dt(updated),
            open_price=_positive((item.get("prevDay") or {}).get("c")),
        )
        self._last_seen[ticker] = updated

    # ------------------------------------------------------------------ EOD mode (free tier)

    async def _poll_eod(self) -> None:
        today = datetime.now(NY).date()
        if self._eod is None:
            self._eod = await self._load_two_latest_days(today)
        elif self._eod.day < today:
            # A newer close may be published; one call checks it.
            newest = await self._fetch_grouped(today)
            if newest:
                closes, ts = newest
                self._eod = _EodData(today, closes, self._eod.closes, ts)
        for ticker in self._tickers:
            self._apply_eod(ticker)

    async def _load_two_latest_days(self, start: date) -> _EodData:
        found: list[tuple[date, dict[str, float], datetime]] = []
        day = start
        for _ in range(10):  # covers weekends + holiday clusters
            result = await self._fetch_grouped(day)
            if result:
                found.append((day, *result))
                if len(found) == 2:
                    break
            day -= timedelta(days=1)
        if not found:
            raise RuntimeError("No grouped-daily data found in the last 10 days")
        (d0, closes, ts), prior = found[0], (found[1][1] if len(found) > 1 else {})
        return _EodData(d0, closes, prior, ts)

    async def _fetch_grouped(self, day: date) -> tuple[dict[str, float], datetime] | None:
        await self._throttle()
        resp = await self._get(GROUPED_PATH.format(day=day.isoformat()), params={"adjusted": "true"})
        results = resp.json().get("results") or []
        if not results:
            return None
        closes = {r["T"]: r["c"] for r in results if _positive(r.get("c"))}
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
            open_price=eod.prior_closes.get(ticker),  # None → falls back to the close itself (0% change)
        )
        self._last_seen[ticker] = eod.day

    async def _throttle(self) -> None:
        """Free tier: at most 5 calls in any rolling 60 s window."""
        now = time.monotonic()
        while self._call_times and now - self._call_times[0] >= 60:
            self._call_times.popleft()
        if len(self._call_times) >= self.FREE_TIER_CALLS_PER_MINUTE:
            await asyncio.sleep(60 - (now - self._call_times[0]) + 0.1)
        self._call_times.append(time.monotonic())

    # ------------------------------------------------------------------ http

    async def _get(self, path: str, *, params: dict, raise_for_status: bool = True) -> httpx.Response:
        resp = await self._client.get(path, params=params)
        if raise_for_status:
            resp.raise_for_status()
        return resp
```

Notes:

- The mode-detection call isn't throttled. On a free key, a cold start costs 1 (detect) + 2–5 (grouped days) calls, so it may wait up to ~60 s for its last grouped call. Prices appear once the first poll finishes. Until then the UI shows `null` prices and trades return `NO_PRICE`, as `PLAN.md` §7 specifies.
- In EOD mode prices don't move intraday. The UI will look static, which is correct for a free key. The README should point users who want motion to the simulator or a paid plan.
- `stop()` cancels the task even while it is inside `_throttle()`'s sleep. `CancelledError` is a `BaseException` and isn't caught by `except Exception`.

---

## 9. `SimulatorDataSource` (summary)

Full design and code: `MARKET_SIMULATOR.md`. Interface-relevant behaviour:

- `start(tickers)` seeds every ticker into the cache **right away** (so the first SSE event is full), then starts a 500 ms tick task.
- Each tick advances every tracked ticker and writes it to the cache with `timestamp=now`. Every tick therefore changes every ticker, as `PLAN.md` §6 describes for the simulator.
- `add_ticker` never raises `UnknownTickerError`. Known tickers use their seed price; unknown ones get a random price from $50 to $300 (`PLAN.md` §6). The price is in the cache before `add_ticker` returns.
- `open_price` = the first price this session (the cache's default behaviour; the simulator never passes `open_price`).

---

## 10. Keeping the priced set = watchlist ∪ positions

One helper, called after any change to the watchlist or positions:

```python
# backend/app/market/priced.py
from .interface import MarketDataSource


async def sync_priced_tickers(db, source: MarketDataSource, user_id: str = "default") -> None:
    """Price exactly the union of watched and held tickers (PLAN.md §6 'Which Tickers Are Priced')."""
    watched = {r["ticker"] for r in await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = ?", (user_id,))}
    held = {r["ticker"] for r in await db.fetch_all("SELECT ticker FROM positions WHERE user_id = ?", (user_id,))}
    await source.sync(watched | held)
```

(`db.fetch_all` stands in for whatever DB helper the backend agent writes.)

Where each route plugs in:

| Operation | Market calls, in order |
|---|---|
| **Add to watchlist** | `t = normalize_ticker(raw)` → `await source.add_ticker(t)` (raises `UnknownTickerError` → 400 `UNKNOWN_TICKER`, nothing written to DB) → insert row → return entry built from `cache.get(t)` |
| **Remove from watchlist** | delete row (404 `NOT_FOUND` if absent) → `await sync_priced_tickers(...)` (keeps `t` priced if still held) |
| **Trade** | `t = normalize_ticker(raw)` → `await source.add_ticker(t)` *(gets an unwatched, unheld ticker priced so it can fill; `UnknownTickerError` → `UNKNOWN_TICKER`)* → under the trade lock: `cache.get(t)` (None → `NO_PRICE`) → execute → `await sync_priced_tickers(...)` *(drops `t` again if the trade failed or it was fully sold and isn't watched)* |
| **Chat actions** | same as the manual trade / watchlist paths, action by action |
| **Reset** | reset DB → `await sync_priced_tickers(...)` (back to the 10 defaults) |
| **Startup** | `source.start(watched ∪ held)` read from DB in the lifespan hook |

Using `add_ticker` before a trade covers `PLAN.md` §7 "Buying a ticker that isn't on the watchlist is allowed… the ticker becomes priced because it is now held". Without it, an unwatched ticker would never have a cached price and the buy could never fill.

### Reading prices elsewhere

```python
update = cache.get("AAPL")             # PriceUpdate | None
price = cache.get_price("AAPL")        # float | None
current = price if price is not None else position.avg_cost   # portfolio fallback, PLAN.md §8
watch_entry = {"ticker": t, **(update.to_dict() if update else {
    "price": None, "previous_price": None, "open_price": None,
    "change_percent": None, "direction": None, "timestamp": None})}
```

---

## 11. SSE endpoint

```python
# backend/app/market/stream.py
import asyncio
import json
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

TICK_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0

stream_router = APIRouter()


async def price_events(cache: PriceCache, request: Request):
    """Yield SSE frames per PLAN.md §6: full set on connect, then only changed tickers; skip empty ticks."""
    yield "retry: 1000\n\n"  # EventSource reconnect delay
    sent: dict[str, datetime] = {}  # ticker -> timestamp last sent to *this* client
    first = True
    seen_version = -1
    last_frame = time.monotonic()

    while not await request.is_disconnected():
        if cache.version != seen_version:
            seen_version = cache.version
            snap = cache.snapshot()
            for gone in sent.keys() - snap.keys():
                del sent[gone]
            changed = {
                t: u.to_dict()
                for t, u in snap.items()
                if first or sent.get(t) != u.timestamp
            }
            if changed:
                for t in changed:
                    sent[t] = snap[t].timestamp
                first = False
                last_frame = time.monotonic()
                yield f"data: {json.dumps(changed, separators=(',', ':'))}\n\n"

        if time.monotonic() - last_frame >= KEEPALIVE_SECONDS:
            last_frame = time.monotonic()
            yield ": keepalive\n\n"  # comment frame; keeps proxies from closing quiet Massive streams

        await asyncio.sleep(TICK_SECONDS)


@stream_router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    cache: PriceCache = request.app.state.price_cache
    return StreamingResponse(
        price_events(cache, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

- `first` stays `True` until one non-empty frame has gone out. A client that connects before Massive's first poll still gets the full set as its first `data:` event.
- Removed tickers simply stop appearing. The frontend drops tickers that leave the watchlist when it refetches `GET /api/watchlist`.

---

## 12. Lifespan wiring

```python
# backend/app/main.py (excerpt)
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.market import PriceCache, create_market_data_source, stream_router
from app.database import init_db, get_db           # backend agent's module
from app.snapshots import run_snapshot_task        # 30 s portfolio snapshots


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()                              # create schema + seed if needed (PLAN.md §7)
    cache = PriceCache()
    source = create_market_data_source(cache)

    watched = {r["ticker"] for r in await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id='default'")}
    held = {r["ticker"] for r in await db.fetch_all("SELECT ticker FROM positions WHERE user_id='default'")}
    await source.start(watched | held)

    app.state.db, app.state.price_cache, app.state.market = db, cache, source
    snapshot_task = asyncio.create_task(run_snapshot_task(db, cache))
    try:
        yield
    finally:
        snapshot_task.cancel()
        await source.stop()
        await db.close()


app = FastAPI(lifespan=lifespan)
app.include_router(stream_router)
# ... other /api routers ...
app.mount("/", StaticFiles(directory="static", html=True), name="static")  # last (PLAN.md §11)
```

Routes get the cache and source through `request.app.state` (or small `Depends` helpers that return them).

---

## 13. Testing

**Shared contract suite** — one parametrized pytest module runs against both implementations (Massive with an `httpx.MockTransport` fake):

```python
@pytest.fixture(params=["simulator", "massive_snapshot", "massive_eod"])
async def source(request, cache):
    src = make_source(request.param, cache)   # builds fakes for the Massive variants
    await src.start(["AAPL", "MSFT"])
    await wait_until(lambda: "AAPL" in cache and "MSFT" in cache)
    yield src
    await src.stop()

async def test_remove_drops_from_cache(source, cache):          # C3
    await source.remove_ticker("AAPL")
    await asyncio.sleep(0.6)
    assert "AAPL" not in cache and "AAPL" not in source.tickers

async def test_add_is_idempotent(source):                       # C2
    await source.add_ticker("NVDA"); await source.add_ticker("NVDA")
    assert "NVDA" in source.tickers
```

**Unit tests:**
- `PriceUpdate`: `direction`, `change_percent` (including `open_price == 0`), `to_dict()` timestamp ends in `Z`
- `PriceCache`: first update sets `previous_price == open_price == price`; later updates keep `open_price` unless given; rounding to 2 dp; `version` bumps; `remove`
- `normalize_ticker`: `" aapl "` → `"AAPL"`, `"BRK.B"` ok, `"TOOLONGX"`, `"AB1"`, `""` → `InvalidTickerError`
- Massive parsing: `_pick_price` fallback order and zero-skipping; `updated` unchanged → no cache write; 403 on detect → EOD mode; unknown ticker in snapshot → `UnknownTickerError`; grouped-daily walk-back over a weekend; 401 stops the poller; 429 backs off; throttle never allows a 6th call within 60 s
- SSE: first frame has all tickers; frames after that have only changed tickers; no frame when nothing changed; keepalive after 15 s of silence

---

## 14. Departures from / refinements to `PLAN.md`

1. **Free Massive tier is EOD-only.** `PLAN.md` §6 says "Free tier (5 calls/min): poll every 15 seconds". The free plan has no snapshot access and only end-of-day data (`MASSIVE_API.md` §2), so 15 s polling would hit 403s. This design auto-detects the plan and uses grouped-daily EOD data on free keys. **`PLAN.md` §6 should be updated to match.**
2. **`MASSIVE_POLL_INTERVAL`** env var added (default 15 s) for the "configurable interval".
3. **Trades call `add_ticker` before looking up the price**, so buying an unwatched ticker can fill (see §10).
4. **Invalid Massive key:** the app keeps running and logs an error, but no prices stream. It does *not* silently fall back to the simulator, because showing fake prices to someone who configured real data would be misleading.
