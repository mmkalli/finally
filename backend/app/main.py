"""FinAlly FastAPI app: `cd backend && uv run uvicorn app.main:app --port 8000`."""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import chat, health, portfolio, watchlist
from app.database import connect, init_db
from app.errors import register_error_handlers
from app.market import PriceCache, create_market_data_source, load_priced_tickers, stream_router
from app.snapshots import run_snapshot_loop

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"  # Next.js export output, copied here by the Dockerfile (PLAN.md §11)

log = logging.getLogger(__name__)

# Local runs read <repo>/.env; in Docker the variables come from --env-file and this is a no-op.
load_dotenv(REPO_ROOT / ".env", override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = connect()
    init_db(db)
    cache = PriceCache()
    market = create_market_data_source(cache)
    await market.start(load_priced_tickers(db))
    log.info("Market data source: %s", market.name)

    app.state.db = db
    app.state.price_cache = cache
    app.state.market = market
    app.state.lock = asyncio.Lock()  # one process-wide lock (PLAN.md §7); see app/api/__init__.py
    snapshots = asyncio.create_task(run_snapshot_loop(db, cache, app.state.lock), name="portfolio-snapshots")
    try:
        yield
    finally:
        snapshots.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await snapshots
        await market.stop()
        db.close()


def create_app(static_dir: Path | None = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="FinAlly", lifespan=lifespan)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(stream_router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(chat.router)

    # Last, so the catch-all mount at / never shadows /api routes
    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
