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
