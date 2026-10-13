import json
from types import SimpleNamespace

import pytest

from app import chat
from app.chat import (
    APOLOGY_MESSAGE,
    HISTORY_LIMIT,
    MOCK_DEFAULT_MESSAGE,
    NOT_CONFIGURED_MESSAGE,
    UNAVAILABLE_MESSAGE,
    LLMReply,
    mock_reply,
    parse_reply,
)
from app.database import DEFAULT_WATCHLIST


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests never reach OpenRouter: env is controlled and an unexpected LLM call fails loudly."""
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    async def unexpected(*args, **kwargs):
        raise AssertionError("acompletion must not be called in this test")

    monkeypatch.setattr(chat, "acompletion", unexpected)


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def llm(monkeypatch):
    """Configured-but-stubbed LLM: set `.reply` (str, or an exception to raise); sent prompts land in `.calls`."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    stub = SimpleNamespace(reply=None, calls=[])

    async def fake_call_llm(messages):
        stub.calls.append(messages)
        if isinstance(stub.reply, Exception):
            raise stub.reply
        return stub.reply

    monkeypatch.setattr(chat, "call_llm", fake_call_llm)
    return stub


def reply_json(message="ok", trades=(), watchlist_changes=()) -> str:
    return json.dumps({"message": message, "trades": list(trades), "watchlist_changes": list(watchlist_changes)})


def send(client, message: str) -> dict:
    r = client.post("/api/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def stored_messages(client) -> list[tuple]:
    rows = client.app.state.db.execute("SELECT role, content, actions FROM chat_messages ORDER BY rowid").fetchall()
    return [tuple(row) for row in rows]


def cash(client) -> float:
    return client.get("/api/portfolio").json()["cash_balance"]


def watchlist(client) -> list[str]:
    return [e["ticker"] for e in client.get("/api/watchlist").json()["tickers"]]


# ---- structured output parsing ----

def test_parse_valid_reply():
    reply = parse_reply(reply_json(
        "Buying", [{"ticker": "AAPL", "side": "buy", "quantity": 10}], [{"ticker": "PYPL", "action": "add"}]
    ))
    assert reply.message == "Buying"
    assert [(t.ticker, t.side, t.quantity) for t in reply.trades] == [("AAPL", "buy", 10.0)]
    assert [(w.ticker, w.action) for w in reply.watchlist_changes] == [("PYPL", "add")]


def test_parse_accepts_empty_arrays_code_fences_and_any_case_enums():
    fenced = "```json\n" + reply_json("hi", [{"ticker": "aapl", "side": "SELL", "quantity": "2.5"}],
                                      [{"ticker": "V", "action": " Remove "}]) + "\n```"
    reply = parse_reply(fenced)
    assert reply.trades[0].side == "sell" and reply.trades[0].quantity == 2.5
    assert reply.watchlist_changes[0].action == "remove"
    assert parse_reply(reply_json("just talk")) == LLMReply(message="just talk", trades=[], watchlist_changes=[])


@pytest.mark.parametrize("raw", [
    "I think you should buy AAPL.",                                         # not JSON
    '{"message": "hi"}',                                                    # missing required arrays
    '{"message": "hi", "trades": [], "watchlist_changes": [], "x": 1}',     # unknown field
    reply_json("hi", [{"ticker": "AAPL", "side": "hold", "quantity": 1}]),  # bad enum
    reply_json("hi", [{"ticker": "AAPL", "side": "buy"}]),                  # trade missing quantity
    '{"message": "truncated", "trades": [',                                 # truncated JSON
])
def test_parse_malformed_returns_raw_text_without_actions(raw):
    assert parse_reply(raw) == LLMReply(message=raw, trades=[], watchlist_changes=[])


@pytest.mark.parametrize("raw", [None, "", "   \n"])
def test_parse_empty_returns_apology(raw):
    assert parse_reply(raw) == LLMReply(message=APOLOGY_MESSAGE, trades=[], watchlist_changes=[])


def test_schema_requires_all_three_fields_and_forbids_extras():
    schema = LLMReply.model_json_schema()
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
    assert schema["additionalProperties"] is False


# ---- mock patterns (PLAN.md §9) ----

@pytest.mark.parametrize("text, message, trades, changes", [
    ("buy 10 AAPL", "Mock: buying 10 AAPL.", [("AAPL", "buy", 10.0)], []),
    ("Please BUY 0.5 tsla now", "Mock: buying 0.5 TSLA.", [("TSLA", "buy", 0.5)], []),
    ("buy 1 aapl.", "Mock: buying 1 AAPL.", [("AAPL", "buy", 1.0)], []),
    ("sell 3 nvda", "Mock: selling 3 NVDA.", [("NVDA", "sell", 3.0)], []),
    ("buy 2 brk.b", "Mock: buying 2 BRK.B.", [("BRK.B", "buy", 2.0)], []),
    ("add pypl", "Mock: adding PYPL to your watchlist.", [], [("PYPL", "add")]),
    ("Watch PYPL please", "Mock: adding PYPL to your watchlist.", [], [("PYPL", "add")]),
    ("remove meta", "Mock: removing META from your watchlist.", [], [("META", "remove")]),
    ("sell 1 AAPL then buy 2 MSFT", "Mock: buying 2 MSFT.", [("MSFT", "buy", 2.0)], []),  # table order wins
    ("remove V and add PYPL", "Mock: adding PYPL to your watchlist.", [], [("PYPL", "add")]),
    ("hello there", MOCK_DEFAULT_MESSAGE, [], []),
    ("show my watchlist", MOCK_DEFAULT_MESSAGE, [], []),
    ("buy AAPL", MOCK_DEFAULT_MESSAGE, [], []),  # no quantity -> no pattern
])
def test_mock_patterns(text, message, trades, changes):
    reply = mock_reply(text)
    assert reply.message == message
    assert [(t.ticker, t.side, t.quantity) for t in reply.trades] == trades
    assert [(w.ticker, w.action) for w in reply.watchlist_changes] == changes


# ---- POST /api/chat in mock mode (full execution path) ----

def test_mock_buy_executes_trade_and_stores_both_messages(client, mock_mode):
    body = send(client, "buy 1 AAPL")
    assert body["message"] == "Mock: buying 1 AAPL."
    [action] = body["actions"]
    assert action == {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 1.0,
                      "price": action["price"], "status": "ok"}
    assert action["price"] > 0
    assert cash(client) == pytest.approx(10000 - action["price"], abs=0.01)
    assert [p["ticker"] for p in client.get("/api/portfolio").json()["positions"]] == ["AAPL"]

    (user_role, user_text, user_actions), (bot_role, bot_text, bot_actions) = stored_messages(client)
    assert (user_role, user_text, user_actions) == ("user", "buy 1 AAPL", None)
    assert (bot_role, bot_text) == ("assistant", "Mock: buying 1 AAPL.")
    assert json.loads(bot_actions) == body["actions"]


def test_mock_failed_trade_is_200_with_error_action(client, mock_mode):
    body = send(client, "sell 5 TSLA")
    assert body["actions"] == [{
        "type": "trade", "ticker": "TSLA", "side": "sell", "quantity": 5.0, "status": "error",
        "error": "Insufficient shares: you hold 0 TSLA", "code": "INSUFFICIENT_SHARES",
    }]
    assert cash(client) == 10000.0
    assert json.loads(stored_messages(client)[1][2]) == body["actions"]


@pytest.mark.parametrize("text, code", [
    ("buy 1000000 AAPL", "INSUFFICIENT_CASH"),
    ("buy 0 AAPL", "INVALID_QUANTITY"),
    ("buy 1 TOOLONGX", "INVALID_TICKER"),
])
def test_mock_trade_errors(client, mock_mode, text, code):
    [action] = send(client, text)["actions"]
    assert action["status"] == "error" and action["code"] == code and action["error"]


def test_mock_watchlist_add_and_remove(client, mock_mode):
    assert send(client, "add pypl")["actions"] == [
        {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"}]
    assert watchlist(client) == DEFAULT_WATCHLIST + ["PYPL"]
    assert send(client, "remove AAPL")["actions"] == [
        {"type": "watchlist", "ticker": "AAPL", "action": "remove", "status": "ok"}]
    assert "AAPL" not in watchlist(client)
    [action] = send(client, "remove AAPL")["actions"]
    assert action["status"] == "error" and action["code"] == "NOT_FOUND"


def test_mock_default_reply_has_no_actions(client, mock_mode):
    assert send(client, "how am I doing?") == {"message": MOCK_DEFAULT_MESSAGE, "actions": []}


def test_reset_clears_chat_history(client, mock_mode):
    send(client, "hello")
    client.post("/api/reset")
    assert stored_messages(client) == []


# ---- not configured ----

def test_without_api_key_returns_not_configured_message(client):
    assert send(client, "buy 1 AAPL") == {"message": NOT_CONFIGURED_MESSAGE, "actions": []}
    assert cash(client) == 10000.0


def test_blank_api_key_counts_as_missing(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "  ")
    assert send(client, "hi")["message"] == NOT_CONFIGURED_MESSAGE


def test_mock_mode_wins_over_missing_key(client, mock_mode):
    assert send(client, "hi")["message"] == MOCK_DEFAULT_MESSAGE


# ---- live path with a stubbed LLM ----

def test_failed_actions_do_not_abort_the_rest(client, llm):
    llm.reply = reply_json(
        "Working on it",
        trades=[
            {"ticker": "aapl", "side": "buy", "quantity": 2},
            {"ticker": "TSLA", "side": "sell", "quantity": 5},       # not held
            {"ticker": "bad ticker", "side": "buy", "quantity": 1},  # invalid format
            {"ticker": "MSFT", "side": "buy", "quantity": 1},
        ],
        watchlist_changes=[
            {"ticker": "ZZZZZZZ", "action": "add"},  # invalid format
            {"ticker": "pypl", "action": "add"},
            {"ticker": "NOPE", "action": "remove"},  # not watched
            {"ticker": "V", "action": "remove"},
        ],
    )
    body = send(client, "do several things")
    assert body["message"] == "Working on it"
    summary = [(a["type"], a["ticker"], a["status"], a.get("code")) for a in body["actions"]]
    assert summary == [
        ("trade", "AAPL", "ok", None),
        ("trade", "TSLA", "error", "INSUFFICIENT_SHARES"),
        ("trade", "BAD TICKER", "error", "INVALID_TICKER"),
        ("trade", "MSFT", "ok", None),
        ("watchlist", "ZZZZZZZ", "error", "INVALID_TICKER"),
        ("watchlist", "PYPL", "ok", None),
        ("watchlist", "NOPE", "error", "NOT_FOUND"),
        ("watchlist", "V", "ok", None),
    ]
    assert {p["ticker"] for p in client.get("/api/portfolio").json()["positions"]} == {"AAPL", "MSFT"}
    assert watchlist(client) == [t for t in DEFAULT_WATCHLIST if t != "V"] + ["PYPL"]


def test_unexpected_action_exception_is_recorded(client, llm, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("kaput")

    monkeypatch.setattr(chat, "execute_trade", boom)
    llm.reply = reply_json("x", trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}],
                           watchlist_changes=[{"ticker": "PYPL", "action": "add"}])
    actions = send(client, "buy")["actions"]
    assert (actions[0]["status"], actions[0]["code"]) == ("error", "INTERNAL_ERROR")
    assert actions[1]["status"] == "ok"


def test_malformed_llm_reply_returns_raw_text(client, llm):
    llm.reply = "Sure! I'd buy some AAPL."
    assert send(client, "hi") == {"message": "Sure! I'd buy some AAPL.", "actions": []}


def test_empty_llm_reply_returns_apology(client, llm):
    llm.reply = None
    assert send(client, "hi") == {"message": APOLOGY_MESSAGE, "actions": []}


def test_llm_failure_returns_friendly_200(client, llm):
    llm.reply = TimeoutError("upstream timeout")
    assert send(client, "hi") == {"message": UNAVAILABLE_MESSAGE, "actions": []}
    assert [role for role, _, _ in stored_messages(client)] == ["user", "assistant"]


def test_prompt_has_portfolio_context_history_with_actions_and_new_message(client, llm):
    llm.reply = reply_json("Buying 1 AAPL", trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}])
    send(client, "buy 1 AAPL")
    llm.reply = reply_json("You hold AAPL")
    send(client, "what do I hold?")

    messages = llm.calls[1]
    assert messages[0]["role"] == "system" and "FinAlly" in messages[0]["content"]
    context = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert context["portfolio"]["positions"][0]["ticker"] == "AAPL"
    assert context["portfolio"]["cash_balance"] < 10000
    assert [e["ticker"] for e in context["watchlist"]] == DEFAULT_WATCHLIST
    assert context["watchlist"][0]["price"] > 0

    assert messages[2:] == [
        {"role": "user", "content": "buy 1 AAPL"},
        {"role": "assistant", "content": messages[3]["content"]},
        {"role": "user", "content": "what do I hold?"},
    ]
    assert messages[3]["content"].startswith("Buying 1 AAPL\n\n[Action results: ")
    assert '"status": "ok"' in messages[3]["content"]


def test_prompt_includes_only_last_20_messages(client, llm):
    llm.reply = reply_json("ok")
    for i in range(15):  # 30 stored messages
        send(client, f"message {i}")
    history = llm.calls[-1][2:-1]
    assert len(history) == HISTORY_LIMIT
    assert history[0] == {"role": "user", "content": "message 4"}
    assert history[-1] == {"role": "assistant", "content": "ok"}


def test_empty_message_is_rejected(client):
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_REQUEST"


# ---- the LiteLLM call itself (stubbed transport) ----

async def test_call_llm_uses_structured_output_via_openrouter_cerebras(monkeypatch):
    seen = {}

    async def fake_acompletion(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply_json("hi")))])

    monkeypatch.setattr(chat, "acompletion", fake_acompletion)
    messages = [{"role": "user", "content": "hi"}]
    assert await chat.call_llm(messages) == reply_json("hi")
    assert seen["model"] == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    assert seen["response_format"] is LLMReply
    assert seen["extra_body"] == {"provider": {"order": ["cerebras"]}}
    assert seen["reasoning_effort"] == "low"
    assert seen["messages"] == messages
