# backend/tests/market/test_cache_and_tickers.py
from datetime import datetime, timezone

import pytest

from app.market import InvalidTickerError, PriceCache, PriceUpdate, normalize_ticker


def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    u = cache.update("AAPL", 190.123)
    assert (u.price, u.previous_price, u.open_price) == (190.12, 190.12, 190.12)
    assert u.direction == "flat" and u.change_percent == 0.0


def test_later_updates_keep_open_price_and_track_previous():
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    u = cache.update("AAPL", 101.0)
    assert (u.previous_price, u.open_price, u.direction, u.change_percent) == (100.0, 100.0, "up", 1.0)
    u = cache.update("AAPL", 99.0, open_price=98.0)  # explicit open (Massive prev close)
    assert (u.open_price, u.direction) == (98.0, "down")


def test_version_bumps_and_remove():
    cache = PriceCache()
    v0 = cache.version
    cache.update("AAPL", 1.0)
    assert cache.version == v0 + 1
    cache.remove("AAPL")
    cache.remove("AAPL")  # no-op
    assert cache.version == v0 + 2 and "AAPL" not in cache and cache.get_price("AAPL") is None


def test_to_dict_shape():
    ts = datetime(2026, 10, 12, 14, 3, 21, 512000, tzinfo=timezone.utc)
    d = PriceUpdate("AAPL", 190.12, 190.05, 189.50, ts).to_dict()
    assert d == {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "open_price": 189.5,
                 "change_percent": 0.33, "direction": "up", "timestamp": "2026-10-12T14:03:21.512Z"}


def test_zero_open_price():
    assert PriceUpdate("X", 1.0, 1.0, 0.0, datetime.now(timezone.utc)).change_percent == 0.0


@pytest.mark.parametrize("raw,expected", [(" aapl ", "AAPL"), ("brk.b", "BRK.B"), ("V", "V")])
def test_normalize_ok(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "TOOLONG", "AB1", "BRK-B", None, 123])
def test_normalize_rejects(raw):
    with pytest.raises(InvalidTickerError) as e:
        normalize_ticker(raw)
    assert e.value.code == "INVALID_TICKER"
