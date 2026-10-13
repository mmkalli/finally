# backend/app/market/stream.py
import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

TICK_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0

stream_router = APIRouter()


async def price_events(cache: PriceCache, request: Request) -> AsyncIterator[str]:
    """SSE frames per PLAN.md §6: every ticker on connect, then only changed tickers; empty ticks skipped."""
    yield "retry: 1000\n\n"  # EventSource reconnect delay (ms)
    sent: dict[str, datetime] = {}  # ticker -> timestamp last sent to this client
    first = True
    seen_version = -1
    last_frame = time.monotonic()

    while not await request.is_disconnected():
        if cache.version != seen_version:
            seen_version = cache.version
            snap = cache.snapshot()
            for gone in sent.keys() - snap.keys():
                del sent[gone]  # so a re-added ticker is sent again
            changed = {t: u for t, u in snap.items() if first or sent.get(t) != u.timestamp}
            if changed:
                sent.update({t: u.timestamp for t, u in changed.items()})
                first = False
                last_frame = time.monotonic()
                payload = {t: u.to_dict() for t, u in changed.items()}
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"

        if time.monotonic() - last_frame >= KEEPALIVE_SECONDS:
            last_frame = time.monotonic()
            yield ": keepalive\n\n"  # comment frame; stops proxies closing a quiet Massive stream

        await asyncio.sleep(TICK_SECONDS)


@stream_router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    return StreamingResponse(
        price_events(request.app.state.price_cache, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
