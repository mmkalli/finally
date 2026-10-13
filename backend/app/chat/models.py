from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    """Structured output the LLM must return (PLAN.md §9). All fields required for strict modes."""

    model_config = ConfigDict(extra="forbid")

    message: str
    trades: list[TradeRequest]
    watchlist_changes: list[WatchlistChange]
