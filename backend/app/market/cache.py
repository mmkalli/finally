from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
            if prev and timestamp <= prev.timestamp:
                # coarse clocks (Windows) can repeat a value; the SSE stream detects changes by timestamp
                timestamp = prev.timestamp + timedelta(microseconds=1)
        update = PriceUpdate(
            ticker=ticker,
            price=price,
            previous_price=prev.price if prev else price,
            open_price=round(open_price, 2),
            timestamp=timestamp,
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
