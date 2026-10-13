import pytest

from app.chat.mock import DEFAULT_MESSAGE, mock_response


@pytest.mark.parametrize("text, message, trade", [
    ("buy 10 AAPL", "Mock: buying 10 AAPL.", ("AAPL", "buy", 10.0)),
    ("Please BUY 1 aapl now", "Mock: buying 1 AAPL.", ("AAPL", "buy", 1.0)),
    ("buy 0.5 brk.b", "Mock: buying 0.5 BRK.B.", ("BRK.B", "buy", 0.5)),
    ("sell 5 TSLA", "Mock: selling 5 TSLA.", ("TSLA", "sell", 5.0)),
    ("Sell 2.25 msft", "Mock: selling 2.25 MSFT.", ("MSFT", "sell", 2.25)),
])
def test_trade_patterns(text, message, trade):
    r = mock_response(text)
    assert r.message == message
    assert [(t.ticker, t.side, t.quantity) for t in r.trades] == [trade]
    assert r.watchlist_changes == []


@pytest.mark.parametrize("text, ticker", [("add PYPL", "PYPL"), ("watch pypl", "PYPL"), ("Add uber please", "UBER")])
def test_add_patterns(text, ticker):
    r = mock_response(text)
    assert r.message == f"Mock: adding {ticker} to your watchlist."
    assert [(w.ticker, w.action) for w in r.watchlist_changes] == [(ticker, "add")]
    assert r.trades == []


def test_remove_pattern():
    r = mock_response("Remove nflx")
    assert r.message == "Mock: removing NFLX from your watchlist."
    assert [(w.ticker, w.action) for w in r.watchlist_changes] == [("NFLX", "remove")]


@pytest.mark.parametrize("text", ["hello", "how is my portfolio?", "buy AAPL", "sell some TSLA", ""])
def test_fallback(text):
    r = mock_response(text)
    assert r.message == DEFAULT_MESSAGE
    assert r.trades == [] and r.watchlist_changes == []


def test_first_pattern_in_table_order_wins():
    # "add" appears first in the text, but buy is earlier in the table.
    r = mock_response("add PYPL and buy 3 AAPL")
    assert r.message == "Mock: buying 3 AAPL."
    r = mock_response("remove V then sell 1 V")
    assert r.message == "Mock: selling 1 V."
