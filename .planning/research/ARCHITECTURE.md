# Architecture Patterns

**Domain:** AI trading workstation (FastAPI + SQLite + SSE + LLM chat; Next.js static export; single container)
**Researched:** 2026-10-13
**Mode:** Brownfield. Only `backend/app/market/` exists. PLAN.md is the locked contract.
**Confidence:** HIGH for backend integration (derived from the existing source and PLAN.md). MEDIUM for LiteLLM and frontend library details (not re-verified here).

## Recommended Architecture

One asyncio event loop, one process, one SQLite connection, one in-memory `PriceCache`. Everything new is a thin layer that reads the cache and the DB and funnels all state mutation through one service function.

```
                       Browser (Next.js static export, same origin)
                         | REST /api/*                  | EventSource /api/stream/prices
                         v                              v
+------------------------------- FastAPI app (app/main.py, lifespan) -----------------------+
|  api/ routers (thin)                                   market/stream.py (EXISTS)           |
|  portfolio, watchlist, chat, system                    reads app.state.price_cache         |
|     |                                                                                      |
|     v                                                                                      |
|  services (the only mutators)                                                              |
|  portfolio/service.py  execute_trade() [asyncio.Lock + BEGIN IMMEDIATE txn]               |
|  watchlist/service.py  add/remove  (source.add_ticker, DB, sync_priced_tickers)            |
|  llm/service.py        chat_turn() -> calls the two services above, in order               |
|     |                         |                                                            |
|     v                         v                                                            |
|  database/ (sqlite3, 1 conn)  market/ (EXISTS): PriceCache <- MarketDataSource.sync()      |
|                                                                                            |
|  background tasks (lifespan): market source task (exists), snapshot_loop (30s)             |
|  StaticFiles(directory="static", html=True) mounted LAST at "/"                            |
+--------------------------------------------------------------------------------------------+
```

### Directory layout to add (follows CONVENTIONS: one package per domain, relative imports, barrel `__init__`)

```
backend/app/
  main.py                 # create_app(), lifespan, exception handler, router includes, static mount
  config.py               # env parsing: DB_PATH, STATIC_DIR, LLM_MOCK, OPENROUTER_API_KEY (one place)
  errors.py               # AppError(code, http_status) base; MarketDataError reparented or handled alongside
  database/
    __init__.py           # connect(), init_db(conn), reset_db(conn)
    schema.py             # CREATE TABLE IF NOT EXISTS ... (PLAN.md section 7)
    seed.py               # default profile + DEFAULT_TICKERS (import from market.seed_data)
  portfolio/
    models.py             # frozen dataclasses: Position, Portfolio, TradeResult
    service.py            # execute_trade, get_portfolio, record_snapshot, get_history
    snapshots.py          # snapshot_loop(app) background task
    errors.py             # InvalidQuantityError, InsufficientCash/SharesError, NoPriceError
  watchlist/
    service.py            # list_watchlist, add_ticker, remove_ticker
  llm/
    schema.py             # Pydantic ChatResponse {message, trades[], watchlist_changes[]}
    prompt.py             # system prompt + portfolio context + history builder
    client.py             # LiteLLM call (isolated, injectable)
    mock.py               # LLM_MOCK regex table, first match wins
    service.py            # chat_turn()
  api/
    portfolio.py, watchlist.py, chat.py, system.py   # APIRouters, validation + translation only
tests/<package>/test_<module>.py
```

### Component Boundaries

| Component | Responsibility | Talks To | Must NOT |
|-----------|---------------|----------|----------|
| `market/*` (exists) | Produce prices, own `PriceCache`, validate tickers | DB only via `priced.py` | Know about portfolio, trades, HTTP bodies |
| `database/` | Schema, seed, connection factory, reset | sqlite3 | Contain business rules |
| `portfolio/service.py` | Sole mutator of cash/positions/trades; builds portfolio view | DB, `PriceCache` (read), `sync_priced_tickers` | Write to cache; be called without the lock held by caller |
| `watchlist/service.py` | Watchlist CRUD with ticker validation and priced-set sync | DB, `MarketDataSource`, `PriceCache` | Insert before the source accepts the ticker |
| `llm/service.py` | One LLM call per message, then execute actions via the two services, persist chat | `llm/client`, `portfolio.service`, `watchlist.service`, DB | Call routers or duplicate trade validation |
| `api/*` routers | Parse request, call service, shape response | services | Hold logic, touch SQL |
| `portfolio/snapshots.py` | Every 30s compute total value and insert snapshot | `portfolio.service.record_snapshot` | Take the trade lock for long, or die on exception |
| `main.py` | Wire: build cache, source, conn, lock; start/stop tasks; include routers; static mount last | everything | Contain domain logic |
| Frontend `lib/` | Price store, portfolio recompute, API client | `/api/*` only | Know about Python |

### Shared state on `app.state` (set in lifespan, read via `request.app.state`)

`price_cache` (REQUIRED name: `stream.py` reads it), `market_source`, `db` (sqlite3 connection), `trade_lock` (asyncio.Lock), `settings`. Inject through small FastAPI dependencies (`get_db`, `get_cache`, `get_source`, `get_lock`) so tests override them with an in-memory DB and a fake source, and tests never need module globals (existing code has none; keep it that way).

## Key Integration Decisions (what the existing code forces)

1. **Use stdlib `sqlite3`, one connection, `check_same_thread=False`, used directly on the event loop.** `priced.py` already takes a `sqlite3.Connection` and runs synchronous queries. Single user and tiny tables make blocking calls sub-millisecond. Do not introduce aiosqlite or an ORM; that would fork the DB access style and force `priced.py` rewrites. Open with `isolation_level=None` (autocommit) and issue explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` in the trade function so transaction scope is visible. Enable `PRAGMA journal_mode=WAL` and `foreign_keys=ON`. Because every DB call is synchronous with no `await` inside a transaction, no other coroutine can interleave mid-transaction; the `asyncio.Lock` is still required because `execute_trade` awaits `source.sync()` (see 3) and the contract says one lock.
2. **`MarketDataError` already carries `code`/`http_status`. Make portfolio and watchlist errors follow the same shape** (class attrs `code`, `http_status`). Cleanest: define a small `AppError(Exception)` base in `app/errors.py` and register ONE exception handler that renders `{"error": str(exc), "code": exc.code}` with `exc.http_status`. Because `MarketDataError` subclasses `ValueError` and is not `AppError`, register the handler for both (`@app.exception_handler(MarketDataError)` and `AppError`), or give both a shared `code`/`http_status` Protocol and handle via one function. Also override `RequestValidationError` (Pydantic 422) to return 400 with the same shape (e.g. `INVALID_QUANTITY` when quantity fails, `INVALID_TICKER` for ticker) so no default FastAPI `{"detail": ...}` body ever leaks (PLAN.md section 8 says every error uses one shape).
3. **Priced-set sync must happen after every DB change that alters watchlist or positions**, not just watchlist edits: a first-time buy of an unwatched ticker makes it held (must be priced); a full sell of an unwatched ticker makes it unpriced. Call `sync_priced_tickers(conn, source)` after the trade COMMIT and after watchlist changes and reset. Do it outside the SQL transaction (it awaits; Massive `add_ticker` can wait on the network) but inside the lock for trades is acceptable because the simulator path is instant; for Massive prefer releasing the lock first (the fill already happened). Decision: sync AFTER releasing the lock; sync is idempotent and eventually consistent.
4. **`MarketDataSource.sync()` swallows `UnknownTickerError`**, so it cannot be the validation point for `POST /api/watchlist`. For add: `normalize_ticker` -> `await source.add_ticker(t)` directly (raises `UnknownTickerError` -> 400 `UNKNOWN_TICKER` in Massive mode) -> insert row (idempotent: `INSERT OR IGNORE`) -> `sync_priced_tickers` is then a no-op safety net. For the LLM path, the same function is used so a failed add shows as an action error.
5. **Trade fill price comes from `cache.get_price(ticker)`; `None` -> `NO_PRICE`.** Never await a price. Buying an unwatched ticker in the simulator works immediately only if the source has been told about it; `add_ticker` seeds a price synchronously there. So for a buy of an unpriced, unwatched ticker the order is: normalize -> cache lookup -> if missing, `NO_PRICE` (do not auto-add). The UI user can add to the watchlist first; this matches PLAN.md ("The backend never waits for a price"). Flag: the E2E test "buy 1 AAPL" uses a default ticker, so this edge is safe.
6. **SSE needs no new code**, only `app.state.price_cache` and `app.include_router(stream_router)`. After a trade or watchlist change, the stream picks up newly priced tickers by cache `version` bump. A removed ticker simply stops appearing (the existing generator drops it from `sent` so re-add resends).
7. **`/api/reset` must also resync the source**: wipe tables (positions, trades, snapshots, chat), set cash 10000, restore the ten default watchlist rows, then `sync_priced_tickers` (this removes any held-only tickers from pricing). Run under the same trade lock. It also should insert one baseline snapshot so the P&L chart has a point right after reset (E2E asserts "P&L chart has data points"). Same for first boot: seed one snapshot at startup.
8. **Merge-conflict markers block everything**: `import app.market` fails today. Resolve first (union in `__init__.py`: export `stream_router`, `load_priced_tickers`, `sync_priced_tickers`). `pyproject.toml` needs new deps added (`litellm`, `pydantic` is transitive, `python-dotenv` optional) and the lockfile regenerated.

## Data Flow

### Price flow (read-only fan-out, exists)
`MarketDataSource` task -> `PriceCache.update()` -> `price_events()` (per-client diff by `timestamp`, 0.5s) -> `EventSource` -> frontend price store (`Map<ticker, number[]>` capped history + latest `PriceUpdate`).

### Trade flow (manual and LLM identical)
```
POST /api/portfolio/trade {ticker, quantity, side}
  router: pydantic parse -> portfolio.service.execute_trade(conn, cache, lock, ticker, qty, side)
    normalize_ticker (INVALID_TICKER)
    round qty to 4dp; <=0 -> INVALID_QUANTITY
    async with lock:
      price = cache.get_price(t) or raise NO_PRICE
      BEGIN IMMEDIATE
        read cash, position
        buy:  cost=round(qty*price,2) > cash -> INSUFFICIENT_CASH
              avg_cost = (old_qty*old_avg + qty*price)/(old_qty+qty); upsert
        sell: qty > held -> INSUFFICIENT_SHARES; qty left <1e-6 -> DELETE row
        cash = round(cash +/- cost, 2)
        INSERT trades; INSERT portfolio_snapshots (total value after trade)
      COMMIT   (ROLLBACK on any exception)
    await sync_priced_tickers(conn, source)       # after lock
    return trade + get_portfolio(conn, cache)
```
Rule: `execute_trade` takes the lock itself (callers never lock) so manual and chat paths cannot forget it; snapshot is inserted inside the same transaction (PLAN.md atomicity wording). Compute `total_value` for the snapshot from the post-trade cash and positions priced from cache (fallback `avg_cost`), the same helper `get_portfolio` uses, so the number never disagrees with the portfolio response.

### Portfolio view (pure function over DB rows + cache)
`get_portfolio(conn, cache)`: `current_price = cache.get_price(t) ?? avg_cost`; market_value, unrealized_pnl, `pnl_percent` rounded as the contract states (money 2dp, quantity 4dp). Keep this as a pure `build_portfolio(cash, positions, prices)` so unit tests need no DB, and so the frontend mirrors the same formulas.

### Chat flow (exactly one LLM call per message)
```
POST /api/chat {message}
  if LLM_MOCK: parsed = mock.match(message)
  elif no OPENROUTER_API_KEY: return 200 {"message": "AI chat isn't configured ...", "actions": []}   # not stored? decide: store neither, simplest
  else: ctx = portfolio + watchlist-with-prices; history = last 20 chat_messages (assistant rows include actions JSON)
        raw = await llm.client.complete(messages, response_format=ChatResponse)   # LiteLLM -> OpenRouter, Cerebras
        parsed = ChatResponse.model_validate_json(raw); on failure -> message=raw or generic apology, no actions
  for t in parsed.trades:            # in order, each independently try/except AppError -> {status:"error", error, code}
        result = await portfolio.service.execute_trade(...)  -> {type:"trade", ..., price, status:"ok"}
  for w in parsed.watchlist_changes: watchlist.service.add/remove -> {type:"watchlist", ticker, action, status}
  INSERT user message; INSERT assistant message with actions JSON
  return {message, actions}
```
Notes: trades run before watchlist changes, matching the PLAN order of fields (trades then watchlist_changes) but the PLAN example lists trade then watchlist; "in order" means array order within each list, with trades first. An LLM trade of an unwatched ticker is allowed. The LiteLLM call is sync-blocking by default: use `litellm.acompletion` so the event loop (and SSE) is not blocked for the duration of the call; also set a timeout (~30s) and catch all exceptions into the "generic apology" path so chat never returns 500. The LLM client module takes the completion callable by injection so tests substitute a fake and mock mode shares the same downstream path (the PLAN says mock results "run through the normal execution path").

### Snapshot flow
`snapshot_loop`: `while True: await asyncio.sleep(30); try: async with lock?` Do NOT take the trade lock for a read-only insert; a single autocommit INSERT cannot interleave with a transaction on the same connection because everything is synchronous on the loop. But one connection with an open BEGIN while the loop awaits is the hazard (see Pitfalls below): trade transactions must contain no `await`, so the snapshot task can never run inside one.

### Frontend data flow
```
EventSource -> priceStore (latest per ticker + bounded history ring, e.g. 600 pts)
   -> watchlist rows (flash class on direction change), sparklines, main chart
GET /api/portfolio (load) + trade/chat/reset responses -> portfolioBase (server snapshot)
   derived = recompute(portfolioBase, priceStore.latest)  // market value, P&L, total, pnl_percent
   -> header total, positions table, heatmap (data-pnl), cash
GET /api/portfolio/history (load + after each trade) -> P&L chart
GET /api/watchlist (load + after add/remove/chat) -> ticker list; prices from SSE
```
Use a small store (Zustand or React context + useSyncExternalStore) rather than component-local state; the SSE store updates twice a second for 10+ tickers and must not re-render the whole tree: selectors per ticker. The recompute logic goes in a pure `lib/portfolio.ts` (unit-tested per PLAN section 12). Heatmap colour scale in `lib/heatmap.ts` (pure, clamp +/-10%, gray at 0).

## Patterns to Follow

### Pattern 1: Service functions take dependencies as arguments
**What:** `execute_trade(conn, cache, lock, source, ...)`; routers pull them from `app.state` via dependencies.
**When:** every service. Matches existing injection style (`client=`, `now=`, `rng=`) and lets pytest use `sqlite3.connect(":memory:")` plus a `PriceCache` populated by hand, no app boot.

### Pattern 2: Pure core, thin async shell
**What:** `build_portfolio`, `apply_buy`, `apply_sell`, mock matcher, prompt builder are pure and sync; I/O wrappers are tiny. Matches `GBMSimulator` / `pick_price`.

### Pattern 3: Lifespan owns startup order
```python
@asynccontextmanager
async def lifespan(app):
    conn = database.connect(settings.db_path)
    database.init_db(conn)                       # schema + seed if empty
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(load_priced_tickers(conn))
    app.state.update(...)   # price_cache, market_source, db, trade_lock
    snap = asyncio.create_task(snapshot_loop(app))
    try: yield
    finally:
        snap.cancel(); await asyncio.gather(snap, return_exceptions=True)
        await source.stop(); conn.close()
```
Order: DB init -> read priced set -> start source -> baseline snapshot (needs a price; the simulator seeds in `start`, Massive may not have one yet, so fall back to `avg_cost`/cash-only value) -> start snapshot task -> yield. Static mount is done in `create_app()` after `include_router` calls (it is route registration, not lifespan work), guarded by `if STATIC_DIR.exists()` so dev and tests work without a frontend build.

### Pattern 4: One error type to HTTP translation point
See decision 2. Routers never build error responses by hand, except `DELETE` 204 with no body.

### Pattern 5: Persist actions JSON verbatim
Store the exact `actions` list returned to the client in `chat_messages.actions`; build history by embedding it in the assistant message text (e.g. appended "[Actions: ...]") so the LLM sees prior failures (PLAN requirement).

## Anti-Patterns to Avoid

### Anti-Pattern 1: `await` inside an open SQLite transaction
**Why bad:** with one shared connection, another coroutine (snapshot task, another request) runs its statements inside your transaction and can commit or roll it back with it.
**Instead:** keep `BEGIN ... COMMIT` blocks fully synchronous (no awaits); do awaits (source sync) before or after.

### Anti-Pattern 2: Routers duplicating trade validation, or the LLM path having its own executor
**Instead:** both call `execute_trade`; the chat service only converts exceptions into action error dicts.

### Anti-Pattern 3: Writing to `PriceCache` from the trade or API layer
(e.g. to "fake" a first price). Single-writer invariant. Use `source.add_ticker`.

### Anti-Pattern 4: Mounting StaticFiles before API routers, or at a prefix
Mounting at `/` with `html=True` first shadows `/api`. Include all routers (including `stream_router`), then mount. Note unknown `/api/...` paths will fall through to static and 404 as HTML; acceptable, or add a catch-all `/api/{path:path}` 404 JSON before the mount.

### Anti-Pattern 5: Next.js features that break static export
No server components needing runtime, no `next/image` optimization (set `images.unoptimized`), no API routes, no `rewrites`. For local dev, proxy `/api` to `localhost:8000` via a dev-only `next.config` rewrite guarded by env var (rewrites are unsupported with `output: 'export'` in build; gate by `NODE_ENV`), or just run the built frontend through FastAPI.

### Anti-Pattern 6: Blocking LLM call on the loop
Use `litellm.acompletion`; a sync `completion` would freeze SSE for seconds.

### Anti-Pattern 7: Per-ticker price in React state at root
Re-renders everything twice a second. Use per-ticker subscriptions.

## Scalability Considerations

Single-user by contract; scale is not a goal. Relevant limits only.

| Concern | Now (1 user) | If multi-user later |
|---------|--------------|---------------------|
| DB access | one connection, sync | `user_id` column already present; swap to per-request connections or aiosqlite |
| Trade lock | one global `asyncio.Lock` | per-user lock dict |
| SSE | per-client diff of shared cache (already efficient) | unchanged |
| Snapshots | 30s insert, ~2.9k rows/day | prune or downsample `GET /history` (cap returned points) |
| Client price history | bounded ring per ticker | unchanged |

## Suggested Build Order (dependency-driven)

1. **Repair + app skeleton.** Resolve merge markers, deps in `pyproject.toml`, `uv sync`, market tests green. Add `main.py` with lifespan wiring only the cache, source, and `stream_router`, plus `/api/health`. Gate: `uvicorn app.main:app` streams prices; the demo path works end to end. (Unblocks everything; also gives the frontend something to connect to.)
2. **Database package.** Schema, seed, init, reset helper; wire into lifespan; `load_priced_tickers` now works. Gate: tests for idempotent init, seed contents, UNIQUE constraints.
3. **Error infrastructure + portfolio service.** `AppError`, handlers (incl. validation override), `build_portfolio`, `execute_trade`, snapshot insert. Pure-logic tests per PLAN section 12 (weighted avg, rounding, sell all, NO_PRICE, insufficient).
4. **Watchlist service + REST routers** (portfolio, trade, history, reset, watchlist, health) and the 30s snapshot task. Gate: API route tests for status codes, shapes, error codes, reset (TestClient with in-memory DB and fake source). After this step the backend is complete minus chat; the frontend can be built against real endpoints.
5. **Chat/LLM.** Pydantic schema, mock matcher, prompt/context/history builder, LiteLLM client, `chat_turn`, `/api/chat`. Mock path first (E2E depends on it), then real client (needs the `cerebras-inference` skill read at this time; verify model name and structured-output support against current LiteLLM and OpenRouter docs).
6. **Frontend** (can start in parallel after step 1 against SSE, and after step 4 for REST). Order inside: price store + SSE status dot + watchlist grid (flash, sparklines) -> header + portfolio recompute lib -> trade bar + positions table -> main chart -> heatmap + P&L chart -> chat panel with inline actions. Pure-logic unit tests as each lib lands.
7. **Packaging.** Static mount wired to `static/`, Dockerfile (Node 20 -> Python 3.12 + uv), `.env.example`, start/stop scripts (PowerShell first).
8. **E2E.** `test/docker-compose.test.yml`, Playwright scenarios from PLAN section 12, `LLM_MOCK=true`, `POST /api/reset` per test.

Parallelism: steps 2-4 (backend core) and the frontend's SSE-only slice can overlap; steps 5 and frontend chat panel are independent given the fixed `/api/chat` contract. Step 7 depends on frontend build output only for the final image, not for earlier steps.

## Contract Details Easy to Get Wrong (checks for plans)

- Watchlist `POST` returns the entry shape with price fields `null` (use `EMPTY_PRICE_FIELDS` from `market/models.py`, already exported) when unpriced.
- `GET /api/watchlist` ordering: by `added_at` so UI rows are stable.
- Trade response includes the full portfolio object; `chat` actions for trades include `price` on ok and `code` on error.
- Empty-string `OPENROUTER_API_KEY` counts as absent; chat message for that case is exact text with an em dash: "AI chat isn't configured — set OPENROUTER_API_KEY in .env to enable it."
- Money rounding: cash after every change `round(x, 2)`; quantity `round(q, 4)`; avoid float drift in avg_cost comparisons in tests with `pytest.approx`.
- Timestamps: reuse `format_timestamp` from `market/models.py` (ISO UTC with Z) for `executed_at`, `recorded_at`, `created_at` so format is uniform.
- `DELETE /api/watchlist/{ticker}` 404 `NOT_FOUND` if not watched; after delete, sync (a held ticker stays priced).
- `.env` loading: backend reads project-root `.env` for local runs (`python-dotenv` or manual parse; in Docker `--env-file` already sets env). `factory.py` reads `os.getenv` directly, so load dotenv BEFORE `create_market_data_source` in lifespan or at import of `main`.
- Windows dev: `tzdata` present (market needs `America/New_York`); SQLite path `db/finally.db` relative to repo root locally, `/app/db` in Docker; make it `DB_PATH` env with those defaults, and `mkdir` the parent.

## Sources

- `planning/PLAN.md` (locked contract) - HIGH
- `.planning/codebase/ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md` - HIGH
- `backend/app/market/{priced,stream,tickers,interface,cache,models,factory,simulator,massive}.py` read directly - HIGH
- LiteLLM `acompletion` and structured-output behaviour via OpenRouter/Cerebras - MEDIUM (training knowledge, not re-verified; confirm in phase research using the `cerebras-inference` skill)
- Next.js `output: 'export'` restrictions (no rewrites, no image optimizer) - MEDIUM (training knowledge; verify at frontend phase)
