# Codebase Concerns

**Analysis Date:** 2026-10-13

## Tech Debt

**Unresolved git merge-conflict markers committed in source files (CRITICAL):**
- Issue: Commit `b3dc60e` ("merge added") committed literal `<<<<<<< HEAD` / `=======` / `>>>>>>> 15bd778...` markers into every market module and `pyproject.toml`. All of these are syntax errors in Python or TOML, so `import app.market` fails and `uv sync` / `uv run pytest` fail.
- Files still conflicted: `backend/app/market/__init__.py`, `backend/app/market/cache.py`, `backend/app/market/demo.py`, `backend/app/market/interface.py`, `backend/app/market/massive.py`, `backend/app/market/models.py`, `backend/app/market/seed_data.py`, `backend/app/market/simulator.py`, `backend/app/market/tickers.py`
- Resolved (2026-10-13, uncommitted): `backend/pyproject.toml` (kept `tzdata`, `[tool.uv] package = false` to match the virtual project in `uv.lock`, plus `testpaths`/`pythonpath`; dropped hatchling) and `backend/app/market/factory.py` (dropped the header comment)
- Not affected: `backend/app/market/stream.py` and `backend/app/market/priced.py` carry no markers (they are the "theirs" side, see below).
- Impact: The existing backend cannot be imported, tested or run. Every later phase that builds on market data is blocked.
- Fix approach: Resolve each hunk by hand:
  - `backend/app/market/__init__.py`: keep the "theirs" side (export `load_priced_tickers`, `sync_priced_tickers`, `stream_router`). `priced.py` and `stream.py` exist, so the HEAD comment saying they "join once the database exists" is stale.
  - Drop the stray `# backend/app/market/<file>.py` header comments from the "theirs" side.
  - `demo.py`: keep the HEAD version (sparkline renderer with a seconds argument).
  - Then regenerate `backend/uv.lock` and run the test suite. Add a CI or pre-commit grep for `^<<<<<<<` so this cannot recur.

**Backend is only the market-data slice; most of the spec is unimplemented:**
- Issue: Only `backend/app/market/` exists in git. There is no `backend/app/main.py`, `api/`, `database/`, `portfolio/` or `chat/` source, and no `frontend/`, `scripts/`, `Dockerfile`, `test/` (E2E), `db/` or `.env.example`.
- Files: `backend/app/` contains only `__init__.py` and `market/`. `README.md` already documents `./scripts/start_mac.sh` and `.env.example`, which do not exist.
- Impact: The app cannot start. `README.md` Quick Start is not runnable.
- Fix approach: Build in the order the spec implies: lifespan and DB init, trade execution, API routes, LLM chat, frontend, Docker and scripts, E2E.

**Stale untracked bytecode from modules that no longer exist:**
- Issue: The working tree has `backend/app/api/__pycache__`, `chat/__pycache__`, `database/__pycache__`, `portfolio/__pycache__`, `app/__pycache__/main.cpython-312.pyc` and `errors.cpython-312.pyc`. The `.py` sources are absent (probably from an earlier, uncommitted branch). They are gitignored (`__pycache__/`).
- Impact: Misleading when listing directories. Python can import orphaned `.pyc` only from legacy sourceless layouts, so this is low risk, but the empty package dirs imply code that is not there.
- Fix approach: Delete the stale dirs. Recover the lost implementation from git history or other branches if it was real (`git log --all -- backend/app/api`).

**Windows tz-database dependency:**
- Issue: `backend/app/market/massive.py` uses `zoneinfo.ZoneInfo("America/New_York")`, which needs `tzdata` on Windows.
- Impact: `tzdata` exists only in the HEAD side of the conflicted `backend/pyproject.toml`. If the other side wins, the module raises `ZoneInfoNotFoundError` on import on Windows.
- Fix approach: Keep `tzdata` in the resolved dependencies.

## Known Bugs

**Package does not install or run as committed:**
- Symptoms: `SyntaxError` on import; TOML parse error on `pyproject.toml`.
- Files: see the merge-conflict entry above.
- Trigger: Any `uv sync`, `uv run`, or `pytest`.
- Workaround: Resolve the markers.

**`PriceCache.update` with `open_price=None` keeps a stale reference after a ticker is removed:**
- Symptoms: Not a bug in itself. `remove()` drops the entry, so a re-added simulator ticker gets a new `open_price` equal to its current seed price, and "daily change %" resets to 0.
- Files: `backend/app/market/cache.py`, `backend/app/market/simulator.py`
- Impact: Matches the spec ("first price recorded in this server session"), but the session reference resets when the user removes and re-adds a ticker. Low severity.

## Spec vs Implementation Gaps (market data)

The market code largely matches `planning/PLAN.md` Section 6. Remaining gaps and risks:

**Ticker validation regex `^[A-Z.]{1,6}$` is applied only through `normalize_ticker`:**
- Files: `backend/app/market/tickers.py`
- Gap: `MarketDataSource.add_ticker` documents that callers pass pre-normalized tickers but does not enforce it. Nothing validates tickers loaded by `load_priced_tickers` (`backend/app/market/priced.py`) from the DB. A malformed DB row flows into Massive request URLs unchanged.
- Fix approach: Call `normalize_ticker` at every API and chat entry point (watchlist add, trade, chat actions). Consider an assertion in `add_ticker`.

**`MarketDataError` carries `http_status` and `code`, but no error handler exists:**
- Files: `backend/app/market/tickers.py`
- Gap: The spec requires `{"error": "...", "code": "..."}` with HTTP 400. No exception handler or app exists yet to map `MarketDataError` to that shape. The `NO_PRICE`, `INSUFFICIENT_CASH`, `INVALID_QUANTITY` and `NOT_FOUND` codes have no home.
- Fix approach: Add a shared errors module and `app.add_exception_handler`. Be aware that FastAPI's default validation errors return 422 with a different shape and must be overridden too.

**SSE event format matches the spec but has unspecified edge behavior:**
- Files: `backend/app/market/stream.py`
- Match: unnamed `data:` events, JSON keyed by ticker, full snapshot on connect, then only changed timestamps, empty ticks skipped.
- Risks:
  - `first = True` only flips when `changed` is non-empty. A client that connects while the cache is empty (no tickers yet) stays in "send everything" mode, which is harmless.
  - A client connecting to an empty cache and then getting only a keepalive could look "connected but empty" to the UI.
  - The change test is `sent.get(t) != u.timestamp`. If the simulator writes several updates with an identical `timestamp` within one tick, the later ones are dropped for that client. Ticks share one `now` per step, so this is fine today. Anything that updates a ticker twice with the same timestamp would be silently skipped.
  - Polling loop with `asyncio.sleep(0.5)` and `request.is_disconnected()`: up to 500 ms latency added to every update and a wakeup per client even when idle. The cache `version` only avoids work, not wakeups. Acceptable for a single user.
  - `Connection: keep-alive` is set as a response header. This is invalid under HTTP/2 and some ASGI servers strip it. Harmless.

**Price source for held-but-unwatched tickers depends on callers:**
- Files: `backend/app/market/priced.py`, `backend/app/market/interface.py`
- Gap: Spec says priced set = watchlist ∪ open positions. `sync_priced_tickers` is a synchronous-sqlite helper taking a `sqlite3.Connection`; nothing calls it. Routes must call it after every watchlist change, trade and reset, or sells of delisted-from-watchlist tickers get `NO_PRICE`. Using a sync `sqlite3` connection inside the async event loop blocks the loop (see Performance).

**Massive mode validates leniently:**
- Files: `backend/app/market/massive.py` (`add_ticker`)
- Gap: Spec says an add is rejected with `UNKNOWN_TICKER` when the API has no data. The code accepts unvalidated tickers when the first poll has not completed within `READY_TIMEOUT` (10 s) or the API call errors. In `eod` (free tier) mode, only tickers in the last grouped-daily result are accepted.
- Impact: Unknown tickers can enter the watchlist during outages and stay with `NO_PRICE` forever. `sync()` in `interface.py` only logs and skips unknown tickers, so a DB watchlist can contain unpriced entries; `GET /api/watchlist` must return null price fields for them (`EMPTY_PRICE_FIELDS` in `backend/app/market/models.py` covers this).
- Also: `add_ticker` blocks the request for up to 10 s waiting for readiness.

**Massive snapshot polling cadence vs spec:**
- Files: `backend/app/market/factory.py`, `backend/app/market/massive.py`
- The spec says "free tier: poll every 15 s". The implementation instead probes snapshot, treats a 403 as free plan, and falls back to end-of-day grouped closes refreshed every 300 s with a 5 calls/min throttle. Free-tier users therefore get static prices (no streaming moves). That is a deliberate deviation. It should be documented in `planning/PLAN.md`. `MASSIVE_POLL_INTERVAL` is an env var that `PLAN.md` Section 5 does not list.
- `MIN_POLL_INTERVAL = 2.0` clamps the configured interval.

**Massive poller can die permanently on 401:**
- Files: `backend/app/market/massive.py` (`_run`)
- On 401 the task returns and sets `_dead`. There is no retry or surfacing to the UI; the SSE stream stays empty and the status dot stays green. `add_ticker` then accepts any ticker unvalidated.
- Fix approach: Surface a health flag via `/api/health` or fall back to the simulator.

## Security Considerations

**API key handling:**
- Risk: `MASSIVE_API_KEY` is passed as a Bearer header in `backend/app/market/massive.py`. Exceptions logged with `%r` (`httpx.HTTPError`) include the request URL but not headers, so the key is not leaked today.
- Current mitigation: Keys come from the environment only. `.env` is gitignored.
- Recommendations: Never log `client.headers`. Add `.env.example` with placeholders only (it does not exist yet).

**No authentication, CORS or rate limiting (by design):**
- Risk: Single-user, no-login design means any process that reaches port 8000 can trade, reset (`POST /api/reset`) and spend `OPENROUTER_API_KEY` credit via `/api/chat`.
- Recommendations: Bind to localhost in the start scripts (`-p 127.0.0.1:8000:8000`). Do not deploy publicly without a gate.

**CI workflows run Claude with repo access:**
- Files: `.github/workflows/claude.yml`, `.github/workflows/claude-code-review.yml`
- Risk: Third-party action permissions and secrets. Review the `permissions:` blocks and trigger conditions (issue and PR comments from arbitrary users).

**Vendored tooling committed into the repo root:**
- Files: `independent-reviewer/hooks/hooks.json`, `.claude-plugin/marketplace.json`
- Risk: Hooks execute commands on developer machines. Review before trusting.

## Performance Bottlenecks

**Blocking sqlite3 in an async app (anticipated):**
- Files: `backend/app/market/priced.py` takes a synchronous `sqlite3.Connection` inside `async def sync_priced_tickers`.
- Cause: Sync DB calls run on the event loop that also drives the simulator tick (500 ms) and SSE.
- Improvement path: Keep queries tiny, or run them with `asyncio.to_thread`. Use WAL mode and a single process-wide `asyncio.Lock` for trades as the spec requires.

**Per-client full-snapshot copy and JSON encoding:**
- Files: `backend/app/market/stream.py`
- Each connected client re-serializes its own changed set every 500 ms. Fine for one user. Cache the serialized payload per cache version if multi-user support is added.

## Fragile Areas

**Time-dependent Massive end-of-day logic:**
- Files: `backend/app/market/massive.py` (`latest_published_day`, `previous_weekday`, `_load_latest_two`)
- Why fragile: Uses a fixed 16:15 ET publish time, weekday-only walkback (`MAX_WALKBACK = 7`), no holiday calendar, and raises `RuntimeError` if no data is found. A late publish yields yesterday's data silently.
- Safe modification: Keep the injectable `now` callable. Extend `backend/tests/market/test_massive.py` and `backend/tests/market/fake_massive.py` before changing.
- Test coverage: Injected `httpx.MockTransport` fakes only. No live API contract test.

**Massive response-shape assumptions:**
- Files: `backend/app/market/massive.py` (`pick_price`, `_apply_snapshot`)
- Relies on `lastTrade.p`, `min.c`, `day.c`, `prevDay.c`, `updated` (nanoseconds) and `T`/`c`/`t` (grouped aggs). Upstream shape changes silently produce no prices (errors are swallowed per contract C7).
- Note: `updated` is assumed to be in nanoseconds. Any change in unit gives wrong timestamps.

**Simulator state is mutated while `add_ticker`/`remove_ticker` may run between ticks:**
- Files: `backend/app/market/simulator.py`
- Single-threaded event loop with no awaits inside `step()`, so this is safe. Do not introduce threads or `await` inside the step loop.

**Order-of-ops coupling to the cache:**
- `SimulatorDataSource.remove_ticker` must remove from the sim before the cache (comment in code). Keep that order.

## Scaling Limits

**In-memory single-process cache and SQLite:**
- Current capacity: One process, one user (`user_id="default"`).
- Limit: Multiple uvicorn workers would each run their own simulator and cache, producing inconsistent prices. Run uvicorn with a single worker.
- Scaling path: Move the cache and data source to a shared service when multi-user support is needed.

## Dependencies at Risk

**Unpinned lower-bounds only:**
- Files: `backend/pyproject.toml`
- Dependencies use `>=` ranges; reproducibility relies on `backend/uv.lock`, which must be regenerated after the conflict is resolved. The LLM dependency (`litellm`) required by Section 9 is not declared anywhere (the HEAD comment mentions it, but it is not in the list), nor is `python-dotenv`.

**Massive (Polygon.io) API:**
- Risk: Third-party endpoint and plan behavior (`api.massive.com`, 403 on free-tier snapshots) documented in `planning/MASSIVE_API.md`. Changes would break the poller silently.

## Missing Critical Features

**Entire application layer:** see "Backend is only the market-data slice" above. Missing: lifespan hook wiring, DB schema and seeding, trade execution with `asyncio.Lock`, portfolio snapshots task (30 s), REST routes, `/api/health`, `LLM_MOCK` mode, structured-output chat, static file serving, Next.js frontend, Dockerfile, scripts, Playwright E2E.

## Test Coverage Gaps

**Existing tests cannot currently run:**
- Files: `backend/tests/market/test_cache_and_tickers.py`, `test_contract.py`, `test_massive.py`, `test_simulator.py`, `test_stream.py`, `fake_massive.py`
- Risk: They import the conflicted modules, so the suite fails at import time. Their real health is unverified until the markers are removed.
- Priority: High. Re-run immediately after resolving conflicts.

**No tests for anything outside `backend/app/market/`:**
- Missing: portfolio math, trade rules, API error shapes, chat and mock parsing, reset, frontend logic (live P&L, heatmap colour scale, flash class), E2E scenarios in `test/`.
- Priority: High as each layer is built (the spec in Section 12 lists required cases).

**No CI test job:**
- Files: `.github/workflows/` has only the two Claude workflows. No pytest or lint run, which is how conflict markers reached `main`-line history unnoticed.
- Priority: High.

**Demo module has no tests:**
- Files: `backend/app/market/demo.py` (terminal renderer). Low priority.

---

*Concerns audit: 2026-10-13*
