import json

import pytest

from app.chat.llm import APOLOGY, parse_response
from app.chat.models import ChatResponse


def test_parses_message_only():
    r = parse_response('{"message": "Hi", "trades": [], "watchlist_changes": []}')
    assert r == ChatResponse(message="Hi", trades=[], watchlist_changes=[])


def test_parses_trades_and_watchlist_changes():
    raw = json.dumps({
        "message": "Buying",
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10},
                   {"ticker": "TSLA", "side": "sell", "quantity": 0.5}],
        "watchlist_changes": [{"ticker": "PYPL", "action": "add"}, {"ticker": "V", "action": "remove"}],
    })
    r = parse_response(raw)
    assert [(t.ticker, t.side, t.quantity) for t in r.trades] == [("AAPL", "buy", 10.0), ("TSLA", "sell", 0.5)]
    assert [(w.ticker, w.action) for w in r.watchlist_changes] == [("PYPL", "add"), ("V", "remove")]


def test_tolerates_code_fences():
    r = parse_response('```json\n{"message": "Hi", "trades": [], "watchlist_changes": []}\n```')
    assert r.message == "Hi"


@pytest.mark.parametrize("raw", [
    "Sure, buying AAPL now!",                                                   # not JSON
    '{"message": "Hi"}',                                                         # missing required arrays
    '{"message": "Hi", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}], "watchlist_changes": []}',
    '{"message": "Hi", "trades": [], "watchlist_changes": [{"ticker": "X", "action": "toggle"}]}',
    '{"message": "Hi", "trades": [{"ticker": "AAPL"}], "watchlist_changes": []}',
    '{"message": "Hi", "trades": [], "watchlist_ch',                             # truncated
])
def test_malformed_falls_back_to_raw_text_without_actions(raw):
    r = parse_response(raw)
    assert r.message == raw
    assert r.trades == [] and r.watchlist_changes == []


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_falls_back_to_apology(raw):
    r = parse_response(raw)
    assert r.message == APOLOGY
    assert r.trades == [] and r.watchlist_changes == []


def test_schema_marks_all_fields_required():
    schema = ChatResponse.model_json_schema()
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}


def test_complete_calls_litellm_with_structured_output(monkeypatch):
    import litellm
    from types import SimpleNamespace

    from app.chat import llm

    seen = {}

    def fake_completion(**kwargs):
        seen.update(kwargs)
        msg = SimpleNamespace(content='{"message": "hi", "trades": [], "watchlist_changes": []}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    assert llm._complete([{"role": "user", "content": "x"}]).startswith('{"message"')
    assert seen["model"] == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    assert seen["response_format"] is ChatResponse
    assert seen["extra_body"] == {"provider": {"order": ["cerebras"]}}
    assert seen["reasoning_effort"] == "low"
