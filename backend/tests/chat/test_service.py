import json

from app.chat.service import NOT_CONFIGURED_MESSAGE, UNAVAILABLE_MESSAGE, handle_chat
from app.database import recent_chat_messages


def reply(message, trades=(), changes=()):
    return json.dumps({"message": message, "trades": list(trades), "watchlist_changes": list(changes)})


# ---- no key / mock ----

async def test_no_key_returns_fixed_message_and_persists(conn, cache, portfolio, env, monkeypatch):
    called = []
    monkeypatch.setattr("app.chat.service.llm._complete", lambda m: called.append(m))
    result = await handle_chat(conn, cache, None, "buy 10 AAPL")
    assert result == {"message": NOT_CONFIGURED_MESSAGE, "actions": []}
    assert called == [] and portfolio.calls == []
    rows = recent_chat_messages(conn)
    assert [(r["role"], r["content"], r["actions"]) for r in rows] == [
        ("user", "buy 10 AAPL", None), ("assistant", NOT_CONFIGURED_MESSAGE, []),
    ]


async def test_blank_key_counts_as_missing(conn, cache, portfolio, env):
    env.setenv("OPENROUTER_API_KEY", "  ")
    result = await handle_chat(conn, cache, None, "hi")
    assert result["message"] == NOT_CONFIGURED_MESSAGE


async def test_mock_mode_executes_trade(conn, cache, portfolio, env):
    env.setenv("LLM_MOCK", "true")
    result = await handle_chat(conn, cache, None, "buy 1 AAPL")
    assert result == {
        "message": "Mock: buying 1 AAPL.",
        "actions": [{"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 1.0, "price": 190.0, "status": "ok"}],
    }


async def test_mock_mode_wins_over_missing_key(conn, cache, portfolio, env):
    env.setenv("LLM_MOCK", "TRUE")
    result = await handle_chat(conn, cache, None, "add PYPL")
    assert result["actions"] == [{"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"}]


async def test_mock_sell_without_shares_reports_error(conn, cache, portfolio, env):
    env.setenv("LLM_MOCK", "true")
    result = await handle_chat(conn, cache, None, "sell 5 AAPL")
    assert result["actions"] == [{
        "type": "trade", "ticker": "AAPL", "side": "sell", "quantity": 5.0, "status": "error",
        "error": "Insufficient shares: you hold 0 AAPL", "code": "INSUFFICIENT_SHARES",
    }]


# ---- live path with a patched completion ----

async def test_actions_run_in_order_and_errors_do_not_abort(conn, cache, portfolio, llm_reply):
    llm_reply(reply(
        "Buying and adjusting your watchlist.",
        trades=[
            {"ticker": "aapl", "side": "buy", "quantity": 10},
            {"ticker": "TSLA", "side": "sell", "quantity": 5},
            {"ticker": "bad ticker!", "side": "buy", "quantity": 1},
            {"ticker": "MSFT", "side": "buy", "quantity": 1000},
            {"ticker": "MSFT", "side": "buy", "quantity": 2},
        ],
        changes=[{"ticker": "PYPL", "action": "add"}, {"ticker": "NFLX", "action": "remove"},
                 {"ticker": "MSFT", "action": "remove"}],
    ))
    result = await handle_chat(conn, cache, None, "do stuff")
    assert result["message"] == "Buying and adjusting your watchlist."
    a = result["actions"]
    assert a[0] == {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 190.0, "status": "ok"}
    assert (a[1]["status"], a[1]["code"]) == ("error", "INSUFFICIENT_SHARES")
    assert (a[2]["status"], a[2]["code"]) == ("error", "INVALID_TICKER")
    assert (a[3]["status"], a[3]["code"]) == ("error", "INSUFFICIENT_CASH")
    assert "price" not in a[3] and a[3]["error"]
    assert a[4]["status"] == "ok" and a[4]["price"] == 410.0
    assert a[5] == {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"}
    assert a[6]["status"] == "error" and a[6]["code"] == "NOT_FOUND"
    assert a[7] == {"type": "watchlist", "ticker": "MSFT", "action": "remove", "status": "ok"}
    # The invalid ticker is rejected before the fake records the call.
    assert [c[0] for c in portfolio.calls] == ["trade"] * 4 + ["add", "remove", "remove"]


async def test_unexpected_exception_becomes_error_action(conn, cache, portfolio, llm_reply, monkeypatch):
    async def boom(*args):
        raise RuntimeError("db exploded")

    monkeypatch.setattr("app.chat.service.execute_trade", boom)
    llm_reply(reply("ok", trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}],
                    changes=[{"ticker": "PYPL", "action": "add"}]))
    result = await handle_chat(conn, cache, None, "go")
    assert result["actions"][0]["status"] == "error" and result["actions"][0]["code"] == "INTERNAL_ERROR"
    assert result["actions"][1]["status"] == "ok"


async def test_malformed_llm_output_returns_raw_text_no_actions(conn, cache, portfolio, llm_reply):
    llm_reply("I think you should buy AAPL.")
    result = await handle_chat(conn, cache, None, "advice?")
    assert result == {"message": "I think you should buy AAPL.", "actions": []}
    assert portfolio.calls == []


async def test_llm_failure_returns_apology(conn, cache, portfolio, llm_reply):
    llm_reply(ConnectionError("network down"))
    result = await handle_chat(conn, cache, None, "hello")
    assert result == {"message": UNAVAILABLE_MESSAGE, "actions": []}
    assert [r["role"] for r in recent_chat_messages(conn)] == ["user", "assistant"]


async def test_persists_user_and_assistant_with_actions(conn, cache, portfolio, llm_reply):
    llm_reply(reply("Buying 1 AAPL.", trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}]))
    result = await handle_chat(conn, cache, None, "buy one apple")
    rows = recent_chat_messages(conn)
    assert [(r["role"], r["content"]) for r in rows] == [("user", "buy one apple"), ("assistant", "Buying 1 AAPL.")]
    assert rows[0]["actions"] is None
    assert rows[1]["actions"] == result["actions"]


# ---- prompt contents ----

async def test_prompt_has_system_context_history_and_new_message(conn, cache, portfolio, llm_reply):
    portfolio.held["AAPL"] = 3
    sent = llm_reply(reply("first", trades=[{"ticker": "TSLA", "side": "sell", "quantity": 1}]))
    await handle_chat(conn, cache, None, "sell my tesla")
    llm_reply(reply("second"))
    await handle_chat(conn, cache, None, "why did that fail?")

    assert len(sent) == 2
    msgs = sent[1]
    assert msgs[0]["role"] == "system" and "FinAlly" in msgs[0]["content"]
    context = msgs[1]["content"]
    assert "Cash: $" in context and "Total value: $" in context
    assert "AAPL: 3 sh" in context                     # position with P&L
    assert "MSFT: $410.00" in context                  # watchlist with live price
    assert msgs[-1] == {"role": "user", "content": "why did that fail?"}
    history = msgs[2:-1]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "sell my tesla"
    assert "INSUFFICIENT_SHARES" in history[1]["content"]   # earlier failure visible to the LLM


async def test_history_limited_to_last_20(conn, cache, portfolio, llm_reply):
    sent = llm_reply(reply("ok"))
    for i in range(12):
        await handle_chat(conn, cache, None, f"msg {i}")
    last = sent[-1]
    history = last[2:-1]
    assert len(history) == 20
    assert history[0]["content"] == "msg 1"
