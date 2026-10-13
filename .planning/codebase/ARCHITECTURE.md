<!-- refreshed: 2026-10-13 -->
# Architecture

**Analysis Date:** 2026-10-13

## Implementation Status

Only the **market data subsystem** of the backend exists (`backend/app/market/`). Everything else in `planning/PLAN.md` is PLANNED and not yet built.

| Area | Status |
|------|--------|
| Market data (simulator, Massive client, cache, SSE route, ticker validation) | EXISTS, `backend/app/market/` |
| Market data unit tests | EXISTS, `backend/tests/market/` |
| FastAPI app entry (`app/main.py`, lifespan, static mount) | PLANNED, absent |
| Database (`backend/app/database/`: schema, seed, init) | PLANNED, absent (`priced.py` already queries `watchlist`/`positions` tables that do not exist yet) |
| Portfolio / trade execution, snapshots task | PLANNED, absent |
| REST routes (`/api/portfolio`, `/api/watchlist`, `/api/chat`, `/api/health`, `/api/reset`) | PLANNED, absent |
| LLM chat (LiteLLM/OpenRouter, mock mode) | PLANNED, absent |
| Frontend (`frontend/`, Next.js static export) | PLANNED, absent |
| `Dockerfile`, `scripts/`, `test/` (Playwright), `db/` | PLANNED, absent |

## System Overview

```text
(PLANNED)  Next.js frontend  --EventSource-->  GET /api/stream/prices
                                                      │
┌─────────────────────────────────────────────────────▼───────────┐
│ EXISTS: `backend/app/market/stream.py`  (stream_router, SSE)     │
│ reads app.state.price_cache (must be set by future lifespan)     │
└─────────────────────────────────────────────────────┬───────────┘
                                                      │ snapshot()/version
┌─────────────────────────────────────────────────────▼───────────┐
│ `backend/app/market/cache.py`  PriceCache (in-memory, 1 writer)  │
└─────────────────────────────────────────────────────▲───────────┘
                                                      │ update()/remove()
┌─────────────────────────────────────────────────────┴───────────┐
│ `backend/app/market/interface.py` MarketDataSource (ABC)         │
│  ├─ `simulator.py` SimulatorDataSource (+ pure GBMSimulator)     │
│  └─ `massive.py`   MassiveDataSource (REST polling, httpx)       │
│ chosen by `factory.py` create_market_data_source() via env       │
└─────────────────────────────────────────────────────▲───────────┘
                                                      │ sync(desired)
                         `priced.py` watchlist ∪ positions (SQLite)
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `PriceUpdate` | Immutable per-ticker price record; derives `change_percent`, `direction`; `to_dict()` = SSE/watchlist JSON shape | `backend/app/market/models.py` |
| `PriceCache` | Latest price per ticker, `version` counter for cheap change detection | `backend/app/market/cache.py` |
| `MarketDataSource` | Abstract interface: `start/stop/add_ticker/remove_ticker/tickers/sync` | `backend/app/market/interface.py` |
| `GBMSimulator` | Pure, synchronous correlated GBM + jump events; seedable rng | `backend/app/market/simulator.py` |
| `SimulatorDataSource` | Async task stepping the simulator every 0.5s into the cache | `backend/app/market/simulator.py` |
| `MassiveDataSource` | Polls Massive REST (snapshot mode on paid plans, EOD grouped-daily mode on free tier), validates tickers | `backend/app/market/massive.py` |
| `create_market_data_source` | Env-driven selection (`MASSIVE_API_KEY`, `MASSIVE_POLL_INTERVAL`) | `backend/app/market/factory.py` |
| `seed_data` | Seed prices, drift/vol, sector correlation loadings, `profile_for()` (random profile for unknown tickers), `DEFAULT_TICKERS` | `backend/app/market/seed_data.py` |
| `tickers` | `normalize_ticker`, regex `^[A-Z.]{1,6}$`, `MarketDataError` hierarchy carrying `code`/`http_status` | `backend/app/market/tickers.py` |
| `priced` | `load_priced_tickers` (SQL union of watchlist and positions), `sync_priced_tickers` | `backend/app/market/priced.py` |
| SSE stream | `stream_router`, `price_events` async generator | `backend/app/market/stream.py` |
| Terminal demo | `python -m app.market.demo` prints live prices/sparklines | `backend/app/market/demo.py` |

## Pattern Overview

**Overall:** Strategy pattern (two interchangeable market data sources behind one ABC) feeding a single shared in-memory cache, with SSE as a read-only fan-out.

**Key Characteristics:**
- Single writer (active `MarketDataSource`), many readers (SSE clients, future trade/portfolio code).
- Everything runs on one asyncio event loop; `PriceCache` methods never await so no lock is needed.
- Pure logic (`GBMSimulator`, `pick_price`, `latest_published_day`) separated from async I/O wrappers for testability.
- Time and HTTP are injectable (`MassiveDataSource(client=, now=)`, `GBMSimulator(rng=)`).
- Background tasks must never die: tick bodies wrapped in `try/except Exception` with `log.exception`.

## Layers

**Domain/value layer:**
- Location: `backend/app/market/models.py`, `tickers.py`, `seed_data.py`
- Depends on: stdlib only
- Used by: all other market modules

**State layer:**
- Location: `backend/app/market/cache.py`
- Depends on: `models.py`

**Source layer:**
- Location: `backend/app/market/interface.py`, `simulator.py`, `massive.py`, `factory.py`
- Depends on: cache, tickers, seed_data, httpx (Massive)

**Delivery layer:**
- Location: `backend/app/market/stream.py` (FastAPI router)
- Depends on: cache; expects `request.app.state.price_cache`

**Integration glue:**
- Location: `backend/app/market/priced.py` (sqlite3 connection + source)

## Data Flow

### Price streaming path

1. A `MarketDataSource` is created by `create_market_data_source(cache)` and `start(tickers)` is called (future lifespan hook; not yet written).
2. Simulator: `_run()` ticks every 0.5s on a fixed cadence, calls `GBMSimulator.step()`, writes each price via `PriceCache.update()` (`simulator.py`). Massive: `_run()` polls snapshot/EOD and writes changed tickers only (`massive.py`).
3. `price_events()` (`stream.py`) loops every 0.5s; when `cache.version` changed it diffs `timestamp` per ticker against what that client was last sent, emits `data: {ticker: PriceUpdate.to_dict()}` frames. First frame has all tickers; empty ticks emit nothing; 15s `: keepalive` comment frames.

### Priced-set sync (planned wiring)

1. Watchlist/trade change -> `sync_priced_tickers(conn, source)` -> `source.sync(watchlist ∪ positions)`.
2. `sync()` adds missing tickers (skips `UnknownTickerError`) and removes extras.

**State Management:** in-memory `PriceCache` only; `open_price` = first price this session (simulator) or previous close (Massive).

## Key Abstractions

**MarketDataSource:** `backend/app/market/interface.py`; contract tests in `backend/tests/market/test_contract.py` apply to both implementations.
**PriceUpdate:** frozen slotted dataclass; JSON shape matches PLAN.md section 6.
**MarketDataError subclasses:** carry `code` and `http_status` so future routes can render `{"error","code"}` bodies.

## Entry Points

**SSE route:** `backend/app/market/stream.py` `GET /api/stream/prices` (router must be included by a future app).
**Demo CLI:** `backend/app/market/demo.py` (`cd backend && uv run python -m app.market.demo [seconds]`).
**App entry:** none yet (PLANNED `backend/app/main.py` with lifespan: init DB, start market source, snapshot task, mount static last).

## Architectural Constraints

- **Threading:** single-threaded asyncio event loop; no worker threads.
- **Global state:** none at module level; cache lives on `app.state.price_cache` (expected, set by future lifespan).
- **Circular imports:** none; `priced.py` imports `interface.py`, not vice versa.
- **Massive free tier:** limited to 5 calls/min, enforced by rolling-window throttle in `massive.py` (`FREE_TIER_CALLS_PER_MINUTE`).
- **Merge conflict markers:** many files in `backend/app/market/` and `backend/pyproject.toml` contain unresolved `<<<<<<< HEAD` / `>>>>>>> 15bd778` markers; they are not importable as-is until resolved. HEAD side includes `tzdata`, `[tool.uv] package = false`; other side includes `priced.py`/`stream_router` exports, hatchling build config, pytest `testpaths`/`pythonpath`.

## Anti-Patterns

### Committing unresolved merge conflicts
**What happens:** `<<<<<<<` markers in source and `pyproject.toml`.
**Why it's wrong:** Python modules fail to import; `uv sync` fails.
**Do this instead:** Resolve to the union (keep `priced`/`stream_router` exports and `tzdata`), remove the `# backend/app/market/<file>.py` header-comment duplicates.

### Writing the cache from outside the active source
**What happens:** n/a currently, but the cache assumes one writer.
**Do this instead:** All writes go through a `MarketDataSource`; readers use `get`, `get_price`, `snapshot`.

## Error Handling

**Strategy:** Domain errors as `MarketDataError` subclasses (`InvalidTickerError`, `UnknownTickerError`); background loops log and continue; Massive degrades to unvalidated adds when the API is slow/unreachable.

## Cross-Cutting Concerns

**Logging:** stdlib `logging`, `log = logging.getLogger(__name__)` per module.
**Validation:** `normalize_ticker()` in `backend/app/market/tickers.py` at every boundary.
**Authentication:** none (single hardcoded `user_id="default"`, planned).

---

*Architecture analysis: 2026-10-13*
