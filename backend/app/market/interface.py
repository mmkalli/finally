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
