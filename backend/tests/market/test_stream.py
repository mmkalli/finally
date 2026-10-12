# backend/tests/market/test_stream.py
import json

from app.market import PriceCache
from app.market import stream as s


class FakeRequest:
    def __init__(self, frames_before_disconnect: int):
        self.left = frames_before_disconnect

    async def is_disconnected(self):
        self.left -= 1
        return self.left < 0


async def collect(cache, ticks, monkeypatch, between=None):
    async def fake_sleep(_):
        if between:
            between.pop(0)() if between else None
    monkeypatch.setattr(s.asyncio, "sleep", fake_sleep)
    return [f async for f in s.price_events(cache, FakeRequest(ticks))]


def data_frames(frames):
    return [json.loads(f[6:]) for f in frames if f.startswith("data: ")]


async def test_first_frame_full_then_only_changes(monkeypatch):
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    steps = [lambda: cache.update("AAPL", 191.0), lambda: None, lambda: cache.update("MSFT", 421.0)]
    frames = await collect(cache, 4, monkeypatch, steps)
    assert frames[0] == "retry: 1000\n\n"
    data = data_frames(frames)
    assert [set(d) for d in data] == [{"AAPL", "MSFT"}, {"AAPL"}, {"MSFT"}]   # empty tick skipped
    assert data[1]["AAPL"]["direction"] == "up"


async def test_empty_cache_waits_for_full_first_frame(monkeypatch):
    cache = PriceCache()
    steps = [lambda: None, lambda: (cache.update("AAPL", 1.0), cache.update("MSFT", 2.0))]
    data = data_frames(await collect(cache, 3, monkeypatch, steps))
    assert [set(d) for d in data] == [{"AAPL", "MSFT"}]


async def test_keepalive(monkeypatch):
    cache = PriceCache()
    clock = [0.0]
    monkeypatch.setattr(s.time, "monotonic", lambda: clock[0])
    steps = [lambda: clock.__setitem__(0, 16.0)]
    frames = await collect(cache, 2, monkeypatch, steps)
    assert ": keepalive\n\n" in frames
