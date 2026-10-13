"""AI chat (PLAN.md §9): portfolio context + history -> one LLM call -> auto-executed actions -> stored messages.

The route (app/api/chat.py) calls `handle_chat`. The LLM reply is structured output matching `LLMReply`;
its trades and watchlist changes run one at a time through the same functions as the manual routes, and each
one's outcome is recorded in `actions`. A failed action never aborts the rest and is never an HTTP error.
"""
import asyncio
import json
import logging
import os
import re
import sqlite3
import uuid
from typing import Literal

from litellm import acompletion
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.database import DEFAULT_USER, utc_now
from app.errors import AppError
from app.market import MarketDataError, MarketDataSource, PriceCache
from app.portfolio import MONEY_DP, execute_trade, get_portfolio
from app.watchlist import add_to_watchlist, list_watchlist, remove_from_watchlist

log = logging.getLogger(__name__)

# cerebras-inference skill: OpenRouter with Cerebras as the provider. LiteLLM needs the "openrouter/" prefix
# to route the PLAN.md §9 model through OpenRouter.
MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
LLM_TIMEOUT_SECONDS = 60

HISTORY_LIMIT = 20
NOT_CONFIGURED_MESSAGE = "AI chat isn't configured — set OPENROUTER_API_KEY in .env to enable it."
APOLOGY_MESSAGE = "Sorry, I couldn't come up with a response. Please try again."
UNAVAILABLE_MESSAGE = "Sorry, the AI service is unavailable right now. Please try again in a moment."

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation (virtual money).

You can:
- Analyze the user's portfolio composition, risk concentration and P&L
- Suggest trades with brief reasoning
- Execute trades when the user asks or agrees (market orders, instant fill at the current price)
- Manage the watchlist proactively (add or remove tickers)

Rules:
- Be concise and data-driven. Use the numbers in the portfolio context.
- Only put trades in "trades" when the user asked for them or agreed to them.
- Quantities are shares (fractional allowed), always positive. Tickers are symbols like AAPL.
- Phrase trade confirmations as intent ("Buying 10 AAPL…"): actions run after you reply and their
  results are shown to the user separately.
- Earlier assistant turns end with "[Action results: …]", added by the system, showing which actions
  succeeded or failed. Never write that block yourself.
- Always respond with valid JSON matching the schema: "message" (your reply), "trades" and
  "watchlist_changes" (use empty arrays when there is nothing to do)."""


# ----------------------------------------------------------------------------- structured output

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # additionalProperties: false, for strict structured-output modes


class TradeOrder(_Strict):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float

    @field_validator("side", mode="before")
    @classmethod
    def _lower_side(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class WatchlistChange(_Strict):
    ticker: str
    action: Literal["add", "remove"]

    @field_validator("action", mode="before")
    @classmethod
    def _lower_action(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class LLMReply(_Strict):
    """PLAN.md §9 schema. Every field is required; "nothing to do" is an empty array."""

    message: str
    trades: list[TradeOrder]
    watchlist_changes: list[WatchlistChange]


_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_reply(raw: str | None) -> LLMReply:
    """Validate the LLM's JSON. On any failure: the raw text (or an apology if empty) with no actions."""
    text = (raw or "").strip()
    if not text:
        return LLMReply(message=APOLOGY_MESSAGE, trades=[], watchlist_changes=[])
    fenced = _CODE_FENCE.match(text)
    try:
        return LLMReply.model_validate_json(fenced.group(1) if fenced else text)
    except ValidationError:
        log.warning("LLM reply failed validation; returning it as plain text")
        return LLMReply(message=text, trades=[], watchlist_changes=[])


# ----------------------------------------------------------------------------- mock mode

_QTY = r"(\d+(?:\.\d+)?|\.\d+)"
_TICKER = r"([A-Za-z][A-Za-z.]*)"

# PLAN.md §9 mock table, in order; the first pattern that matches wins
_MOCK_TRADE = [
    ("buy", re.compile(rf"\bbuy\s+{_QTY}\s+{_TICKER}", re.IGNORECASE), "buying"),
    ("sell", re.compile(rf"\bsell\s+{_QTY}\s+{_TICKER}", re.IGNORECASE), "selling"),
]
_MOCK_WATCH = [
    ("add", re.compile(rf"\b(?:add|watch)\s+{_TICKER}", re.IGNORECASE), "Mock: adding {} to your watchlist."),
    ("remove", re.compile(rf"\bremove\s+{_TICKER}", re.IGNORECASE), "Mock: removing {} from your watchlist."),
]
MOCK_DEFAULT_MESSAGE = "Mock: I'm FinAlly, your AI trading assistant."


def _mock_ticker(raw: str) -> str:
    return raw.rstrip(".").upper()  # "buy 1 aapl." -> AAPL; BRK.B keeps its dot


def mock_reply(user_message: str) -> LLMReply:
    """Deterministic reply for LLM_MOCK=true. It runs through the normal execution path like a real reply."""
    for side, pattern, verb in _MOCK_TRADE:
        if m := pattern.search(user_message):
            qty, ticker = m.group(1), _mock_ticker(m.group(2))
            return LLMReply(
                message=f"Mock: {verb} {qty} {ticker}.",
                trades=[TradeOrder(ticker=ticker, side=side, quantity=float(qty))],
                watchlist_changes=[],
            )
    for action, pattern, template in _MOCK_WATCH:
        if m := pattern.search(user_message):
            ticker = _mock_ticker(m.group(1))
            return LLMReply(
                message=template.format(ticker), trades=[], watchlist_changes=[WatchlistChange(ticker=ticker, action=action)]
            )
    return LLMReply(message=MOCK_DEFAULT_MESSAGE, trades=[], watchlist_changes=[])


# ----------------------------------------------------------------------------- prompt + LLM call

def load_history(conn: sqlite3.Connection, user_id: str = DEFAULT_USER, limit: int = HISTORY_LIMIT) -> list[dict]:
    """The last `limit` chat messages, oldest first, with assistant actions decoded."""
    rows = conn.execute(
        "SELECT role, content, actions FROM chat_messages WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [
        {"role": role, "content": content, "actions": json.loads(actions) if actions else None}
        for role, content, actions in reversed(rows)
    ]


def build_messages(context: dict, history: list[dict], user_message: str) -> list[dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "Current portfolio and watchlist (live prices):\n" + json.dumps(context)},
    ]
    for entry in history:
        content = entry["content"]
        if entry["role"] == "assistant" and entry["actions"]:
            content += "\n\n[Action results: " + json.dumps(entry["actions"]) + "]"
        messages.append({"role": entry["role"], "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


async def call_llm(messages: list[dict]) -> str | None:
    """One structured-output completion via LiteLLM -> OpenRouter (Cerebras). Returns the raw content."""
    response = await acompletion(
        model=MODEL,
        messages=messages,
        response_format=LLMReply,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    return response.choices[0].message.content


def llm_mock_enabled() -> bool:
    return os.getenv("LLM_MOCK", "").strip().lower() == "true"


def llm_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())


# ----------------------------------------------------------------------------- actions

def _error_fields(exc: Exception) -> dict:
    if isinstance(exc, AppError):
        return {"status": "error", **exc.to_dict()}
    if isinstance(exc, MarketDataError):
        return {"status": "error", "error": str(exc), "code": exc.code}
    log.exception("Chat action failed unexpectedly")
    return {"status": "error", "error": "Unexpected error while running this action", "code": "INTERNAL_ERROR"}


def _display_ticker(raw: str) -> str:
    return raw.strip().upper()


async def run_actions(
    conn: sqlite3.Connection,
    cache: PriceCache,
    market: MarketDataSource,
    reply: LLMReply,
    user_id: str = DEFAULT_USER,
) -> list[dict]:
    """Execute trades, then watchlist changes, in order; one outcome per action. Caller holds app.state.lock."""
    actions = []
    for order in reply.trades:
        try:
            trade = await execute_trade(conn, cache, market, order.ticker, order.side, order.quantity, user_id)
        except Exception as exc:  # noqa: BLE001 - a failed action is recorded, and the rest still run
            actions.append({
                "type": "trade", "ticker": _display_ticker(order.ticker), "side": order.side,
                "quantity": order.quantity, **_error_fields(exc),
            })
        else:
            actions.append({
                "type": "trade", "ticker": trade["ticker"], "side": trade["side"],
                "quantity": trade["quantity"], "price": round(trade["price"], MONEY_DP), "status": "ok",
            })
    for change in reply.watchlist_changes:
        action = {"type": "watchlist", "ticker": _display_ticker(change.ticker), "action": change.action}
        try:
            if change.action == "add":
                action["ticker"] = (await add_to_watchlist(conn, cache, market, change.ticker, user_id))["ticker"]
            else:
                action["ticker"] = await remove_from_watchlist(conn, market, change.ticker, user_id)
        except Exception as exc:  # noqa: BLE001
            action.update(_error_fields(exc))
        else:
            action["status"] = "ok"
        actions.append(action)
    return actions


# ----------------------------------------------------------------------------- entry point

def store_exchange(
    conn: sqlite3.Connection, user_message: str, sent_at: str, reply: str, actions: list[dict],
    user_id: str = DEFAULT_USER,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, 'user', ?, NULL, ?)",
            (str(uuid.uuid4()), user_id, user_message, sent_at),
        )
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, 'assistant', ?, ?, ?)",
            (str(uuid.uuid4()), user_id, reply, json.dumps(actions), utc_now()),
        )


async def handle_chat(
    conn: sqlite3.Connection,
    cache: PriceCache,
    market: MarketDataSource,
    lock: asyncio.Lock,
    user_message: str,
    user_id: str = DEFAULT_USER,
) -> dict:
    """POST /api/chat: returns {"message", "actions"} (PLAN.md §8). Never raises for LLM or action failures."""
    sent_at = utc_now()
    if llm_mock_enabled():
        reply = mock_reply(user_message)
    elif not llm_configured():
        reply = LLMReply(message=NOT_CONFIGURED_MESSAGE, trades=[], watchlist_changes=[])
    else:
        context = {"portfolio": get_portfolio(conn, cache, user_id), "watchlist": list_watchlist(conn, cache, user_id)}
        messages = build_messages(context, load_history(conn, user_id), user_message)
        try:
            reply = parse_reply(await call_llm(messages))
        except Exception:  # network/API errors become a friendly message, not a 500
            log.exception("LLM call failed")
            reply = LLMReply(message=UNAVAILABLE_MESSAGE, trades=[], watchlist_changes=[])

    async with lock:
        actions = await run_actions(conn, cache, market, reply, user_id)
        store_exchange(conn, user_message, sent_at, reply.message, actions, user_id)
    return {"message": reply.message, "actions": actions}
