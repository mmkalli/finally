"""System prompt, portfolio context and conversation history for the chat LLM (PLAN.md §9)."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation (virtual money, no real trades).

You can:
- Analyze the user's portfolio composition, risk concentration and unrealized P&L.
- Suggest trades with brief reasoning.
- Execute market orders (buy/sell, fractional quantities allowed) when the user asks or agrees, via "trades".
- Manage the watchlist proactively (add/remove tickers) via "watchlist_changes".

Rules:
- Be concise and data-driven; cite the numbers from the portfolio context.
- Your actions run after you reply, so phrase trade confirmations as intent ("Buying 10 AAPL..."), never as completed.
- Only trade when the user asked for it or agreed to it. Buys need enough cash; sells need enough shares.
- Tickers are uppercase symbols like AAPL or BRK.B.
- Earlier assistant turns list the actions that ran and whether each succeeded or failed; use that to explain failures.
- Always respond with valid JSON matching the schema: {"message": string, "trades": [{"ticker", "side": "buy"|"sell", "quantity"}], "watchlist_changes": [{"ticker", "action": "add"|"remove"}]}. Use empty arrays when there is nothing to do."""


def format_portfolio_context(portfolio: dict, watchlist: list[dict]) -> str:
    lines = [
        "Current portfolio:",
        f"- Cash: ${portfolio['cash_balance']:,.2f}",
        f"- Positions value: ${portfolio['positions_value']:,.2f}",
        f"- Total value: ${portfolio['total_value']:,.2f}",
        f"- Unrealized P&L: ${portfolio['unrealized_pnl']:,.2f}",
        "Positions:",
    ]
    total = portfolio["total_value"] or 0
    for p in portfolio["positions"]:
        weight = p["market_value"] / total * 100 if total else 0
        lines.append(
            f"- {p['ticker']}: {p['quantity']:g} sh, avg cost ${p['avg_cost']:,.2f}, "
            f"price ${p['current_price']:,.2f}, value ${p['market_value']:,.2f} ({weight:.1f}% of portfolio), "
            f"P&L ${p['unrealized_pnl']:,.2f} ({p['pnl_percent']:+.2f}%)"
        )
    if not portfolio["positions"]:
        lines.append("- (none)")
    lines.append("Watchlist (live prices, change since open):")
    for w in watchlist:
        if w.get("price") is None:
            lines.append(f"- {w['ticker']}: no price yet")
        else:
            lines.append(f"- {w['ticker']}: ${w['price']:,.2f} ({w['change_percent']:+.2f}%)")
    if not watchlist:
        lines.append("- (empty)")
    return "\n".join(lines)


def history_messages(history: list[dict]) -> list[dict]:
    """Stored chat rows -> LLM messages. Assistant turns carry their executed actions and outcomes."""
    out = []
    for row in history:
        content = row["content"]
        if row["role"] == "assistant" and row.get("actions"):
            content += f"\n\n[Actions executed after this reply: {json.dumps(row['actions'])}]"
        out.append({"role": row["role"], "content": content})
    return out


def build_messages(portfolio: dict, watchlist: list[dict], history: list[dict], user_message: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": format_portfolio_context(portfolio, watchlist)},
        *history_messages(history),
        {"role": "user", "content": user_message},
    ]
