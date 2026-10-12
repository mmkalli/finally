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
