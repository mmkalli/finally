# backend/app/main.py
"""FastAPI app: lifespan (DB, market data, snapshots), /api routes, SSE stream, static frontend."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_BACKEND_DIR = Path(__file__).resolve().parents[1]
# Locally `.env` lives at the repo root (next to backend/); in Docker it arrives via --env-file.
for env_file in (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env"):
    if env_file.is_file():
        load_dotenv(env_file, override=False)

from app import database as db  # noqa: E402
from app.api import api_router  # noqa: E402
from app.errors import install_error_handlers  # noqa: E402
from app.market import PriceCache, create_market_data_source, load_priced_tickers, stream_router  # noqa: E402
from app.portfolio import record_snapshot  # noqa: E402

log = logging.getLogger(__name__)

SNAPSHOT_SECONDS = 30.0
STATIC_DIR = _BACKEND_DIR / "static"


async def snapshot_loop(conn, cache: PriceCache, interval: float = SNAPSHOT_SECONDS) -> None:
    """Record total portfolio value every `interval` seconds (first one at startup). Never dies."""
    while True:
        try:
            record_snapshot(conn, cache)
        except Exception:
            log.exception("Portfolio snapshot failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    conn = db.get_connection()
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(load_priced_tickers(conn))
    app.state.conn, app.state.cache, app.state.source = conn, cache, source
    snapshots = asyncio.create_task(snapshot_loop(conn, cache), name="portfolio-snapshots")
    try:
        yield
    finally:
        snapshots.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await snapshots
        await source.stop()
        db.close_db()


def create_app() -> FastAPI:
    app = FastAPI(title="FinAlly", lifespan=lifespan)
    install_error_handlers(app)
    # No GZipMiddleware: it buffers the text/event-stream response and SSE prices never arrive.
    app.include_router(api_router)
    app.include_router(stream_router)
    # Mounted last so it never shadows /api. Absent in local dev before a frontend build.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
