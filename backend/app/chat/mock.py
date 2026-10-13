"""Deterministic mock LLM for LLM_MOCK=true (PLAN.md §9 'LLM Mock Mode')."""

from __future__ import annotations

import re

from .models import ChatResponse, TradeRequest, WatchlistChange

_QTY = r"(\d+(?:\.\d+)?|\.\d+)"
_TICKER = r"([A-Za-z.]+)"

# Checked in table order; the first pattern that matches anywhere in the message wins.
_BUY = re.compile(rf"\bbuy\s+{_QTY}\s+{_TICKER}", re.IGNORECASE)
_SELL = re.compile(rf"\bsell\s+{_QTY}\s+{_TICKER}", re.IGNORECASE)
_ADD = re.compile(rf"\b(?:add|watch)\s+{_TICKER}", re.IGNORECASE)
_REMOVE = re.compile(rf"\bremove\s+{_TICKER}", re.IGNORECASE)

DEFAULT_MESSAGE = "Mock: I'm FinAlly, your AI trading assistant."


def mock_response(user_message: str) -> ChatResponse:
    if m := _BUY.search(user_message):
        qty, ticker = m.group(1), m.group(2).upper()
        return ChatResponse(
            message=f"Mock: buying {qty} {ticker}.",
            trades=[TradeRequest(ticker=ticker, side="buy", quantity=float(qty))],
            watchlist_changes=[],
        )
    if m := _SELL.search(user_message):
        qty, ticker = m.group(1), m.group(2).upper()
        return ChatResponse(
            message=f"Mock: selling {qty} {ticker}.",
            trades=[TradeRequest(ticker=ticker, side="sell", quantity=float(qty))],
            watchlist_changes=[],
        )
    if m := _ADD.search(user_message):
        ticker = m.group(1).upper()
        return ChatResponse(
            message=f"Mock: adding {ticker} to your watchlist.",
            trades=[],
            watchlist_changes=[WatchlistChange(ticker=ticker, action="add")],
        )
    if m := _REMOVE.search(user_message):
        ticker = m.group(1).upper()
        return ChatResponse(
            message=f"Mock: removing {ticker} from your watchlist.",
            trades=[],
            watchlist_changes=[WatchlistChange(ticker=ticker, action="remove")],
        )
    return ChatResponse(message=DEFAULT_MESSAGE, trades=[], watchlist_changes=[])
