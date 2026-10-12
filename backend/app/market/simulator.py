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
