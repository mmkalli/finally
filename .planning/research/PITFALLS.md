# Pitfalls Research

**Domain:** AI-powered single-container trading workstation (FastAPI + SQLite + SSE + LiteLLM/OpenRouter backend, Next.js static export, Docker, Playwright E2E, Windows dev host)
**Researched:** 2026-10-13
**Confidence:** MEDIUM overall. The OpenRouter findings were verified live against the OpenRouter API on 2026-10-13 (HIGH). The rest of the framework behaviour comes from established knowledge of FastAPI/Starlette, uvicorn, SQLite, Next.js, Recharts, Playwright and Docker. It was not re-verified against current docs, so treat it as MEDIUM. Items marked (verify) should be checked in the owning phase.

`planning/PLAN.md` is locked. Every prevention below works inside the spec and does not change it. Where the spec is ambiguous, the pitfall says "decide and document" rather than "change the spec".

Phase names below are suggested labels, to be mapped onto the roadmap:
- P0 = Repair and CI
- P1 = Backend core (lifespan, DB, trades, API)
- P2 = LLM chat
- P3 = Frontend
- P4 = Docker and scripts
- P5 = E2E

---

## Critical Pitfalls

### Pitfall 1: The LLM provider/model assumption in PLAN.md is already false (Cerebras is not an endpoint for this model)

**What goes wrong:**
Live check of OpenRouter on 2026-10-13:
- `nvidia/nemotron-3-ultra-550b-a55b:free` has exactly one endpoint, provider "Nvidia". Its `supported_parameters` include `tools` and `tool_choice` but NOT `response_format` or `structured_outputs`.
- The paid `nvidia/nemotron-3-ultra-550b-a55b` is served by DeepInfra, BaseTen and Venice. None of them is Cerebras. Only DeepInfra lists `structured_outputs` and `response_format`. Venice lists `response_format` only.

The skill snippet uses `extra_body={"provider": {"order": ["cerebras"]}}`. `order` is a preference, so with fallbacks allowed OpenRouter silently routes to Nvidia. The request "works", but there is no Cerebras speed and no JSON-schema enforcement. If `allow_fallbacks: false` is set, it returns a 404 "No endpoints found" instead.

Consequences for the app: the model may wrap JSON in prose or code fences, or emit its reasoning text. It may also omit required fields or return an empty `content` (reasoning models can spend the whole budget on reasoning). It can also hit free-tier 429s and daily limits.

**Why it happens:**
The spec and skill were written against a model/provider pairing that has since changed. Free-model endpoints change frequently.

**How to avoid:**
- Do not rely on provider-enforced schemas. Make the pipeline robust to unenforced JSON:
  - Pass `response_format=PydanticModel` (LiteLLM ignores or drops it if unsupported; set `litellm.drop_params = True` or pass `allowed_openai_params` (verify)).
  - Put the JSON schema and one example in the system prompt anyway.
  - Parse tolerantly: strip code fences, extract the first `{...}` block, `model_validate_json`.
  - On failure return raw text or the generic apology with no actions, exactly as PLAN §9 step 5 specifies.
- Keep the provider choice in one constant and one env-overridable place (for example `LLM_MODEL`, with a default of the spec value). Do not hard-code it in call sites. This does not change PLAN.md, it only makes a swap a one-line change.
- Set an explicit `max_tokens` (several thousand) and `reasoning_effort="low"` per the skill. Treat empty `content` as a failure, and fall back to `reasoning_content` only if it contains valid JSON.
- Add a `timeout` (about 30 s), at most 1 retry on 429/5xx, and map every exception (`RateLimitError`, `Timeout`, `AuthenticationError`, `NotFoundError`) to a normal 200 chat response with an apology and no actions. Never return a 500 from `/api/chat`.
- Run a one-off live smoke script (not in CI) in P2 that prints which provider actually served the request (OpenRouter returns `provider` in the response body). Record the result in the phase notes.
- Use `litellm.acompletion` (async) in the route. The sync `completion` from the skill would block the event loop and freeze the SSE stream and simulator for the duration of the call.

**Warning signs:**
- Responses have latency of several seconds or more (not Cerebras-fast).
- `model_validate_json` fails intermittently.
- Content starts with "```json" or "<think>".
- 404 "No endpoints found that can handle the requested parameters".
- 429 bursts during E2E.

**Phase to address:** P2 (live smoke + tolerant parser + async call). Flag P2 for deeper research: confirm current provider routing before coding.

---

### Pitfall 2: Merge-conflict markers and a broken baseline poison everything downstream

**What goes wrong:**
9 market modules contain `<<<<<<<` markers (CONCERNS.md). New code is built on a base that cannot import. Tests "pass" only for files that were not touched. A wrong-side resolution silently drops `stream_router`, `load_priced_tickers` or `sync_priced_tickers`. If `tzdata` is lost, `massive.py` fails on Windows.

**Why it happens:**
There is no CI test job, and `uv.lock` was generated before the merge.

**How to avoid:**
- Resolve per the CONCERNS.md guidance: `__init__.py` takes "theirs", `demo.py` takes HEAD, and the stray header comments are dropped.
- Verify with `grep -rn '^<<<<<<<\|^=======$\|^>>>>>>>' backend/`, then `uv lock`, `uv sync`, `uv run pytest`.
- Add a guard test or pre-commit hook that fails on markers. Add a minimal CI job: `uv sync --frozen && uv run pytest`.
- Add `litellm`, `pydantic`, `python-dotenv` and the DB driver to `pyproject.toml` now. Use `uv add` so the lockfile stays consistent, and keep `tzdata`.
- Delete the stale `__pycache__` dirs for `api/`, `chat/`, `database/` and `portfolio/`. Empty package dirs make an agent believe code exists.

**Warning signs:**
`ImportError`/`SyntaxError`, a lockfile diff after `uv sync`, tests collected but skipped.

**Phase to address:** P0, as a hard gate. Nothing else starts until the market test suite is green.

---

### Pitfall 3: Blocking the event loop (sync sqlite3 and sync LLM call share the loop with the simulator and SSE)

**What goes wrong:**
The simulator ticks every 500 ms and SSE polls every 500 ms on the same loop. A sync `sqlite3` call that waits on a lock, or a sync `litellm.completion` that takes seconds, stalls all of them. Prices freeze, the dot flickers, and E2E "prices are updating" fails intermittently. `priced.py` already takes a sync `sqlite3.Connection` inside an `async def` (CONCERNS.md).

**Why it happens:**
sqlite3 calls are fast most of the time, so the problem hides until the WAL checkpoint or a snapshot write coincides with a trade.

**How to avoid:**
- Pick one DB access strategy and use it everywhere. Either `aiosqlite` (one long-lived connection owned by a small repository layer), or sync `sqlite3` with every call wrapped in `asyncio.to_thread`. In the thread variant open the connection with `check_same_thread=False` and serialize through the single lock or a dedicated single-thread executor.
- Never share one `sqlite3.Connection` across threads without that serialization. Symptoms are "recursive cursor use", "database is locked" and corrupted transaction state.
- Adapt `sync_priced_tickers` to the chosen strategy, and write a test for it.
- Always `await litellm.acompletion(...)`.

**Warning signs:**
The SSE gap between events exceeds about 1 s during a trade or chat call. `database is locked` appears in logs.

**Phase to address:** P1 (decide in the first plan). Verify with a test that fires a slow chat call (mocked with `asyncio.sleep`) while asserting SSE ticks keep arriving.

---

### Pitfall 4: SQLite transaction and lock semantics do not give the atomicity the spec requires

**What goes wrong:**
- Python `sqlite3` implicit transaction handling. In legacy mode (default `isolation_level=""`) it opens a transaction only before DML, not before the SELECT that reads cash. That leaves a read-then-write gap. Python 3.12 adds the `autocommit` attribute, which is cleaner but is a different mode (verify).
- The `asyncio.Lock` only protects code paths that take it. The 30 s snapshot task, `POST /api/reset` and the chat executor can bypass it and race with a trade (for example a snapshot reading cash between the cash update and the position upsert, so a total_value with a hole in it is recorded).
- A failure midway (`INSUFFICIENT_SHARES` raised after the cash update) leaves a half-applied trade if there is no rollback.
- Validation errors must be raised before any write, or inside a `try/except` that rolls back.

**How to avoid:**
- One `execute_trade(ticker, side, qty)` function, used by both the REST route and the chat executor. Inside it: `async with trade_lock`, `BEGIN IMMEDIATE`, read cash and position inside the transaction, validate, write, commit. `try/except` rolls back on any exception.
- Take the same lock in reset, and in the snapshot task when it reads cash+positions (or have the snapshot compute its value inside one read transaction).
- Compute the post-trade snapshot using the in-transaction values, not a second query.
- Enable `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON` (it is per connection), and `PRAGMA busy_timeout=5000`.
- Test with `asyncio.gather` of two simultaneous buys that together exceed cash. Exactly one must succeed.

**Warning signs:**
Cash goes negative or does not equal the sum of trades. Snapshots show dips that revert on the next tick. A trade row exists with no position change.

**Phase to address:** P1.

---

### Pitfall 5: Float money drift and inconsistent rounding break the spec's exact assertions

**What goes wrong:**
- `round()` in Python is binary-float based (`round(2.675, 2)` gives `2.67`) and rounds half to even.
- `cash -= qty * price` accumulates error. Cash goes to `9999.999999999998`, or the "buy exactly all cash" case fails the `quantity × price ≤ cash_balance` check by 1e-12.
- Ambiguity the spec leaves open: the cache holds a price with many decimals (GBM), but the API shows 2 dp and PLAN says fills happen at "the current cached price". If the fill uses the unrounded price but the UI shows the rounded one, the displayed `qty × price` will not match the cash change.
- The sell-all dust rule. Quantity is rounded to 4 dp, but `avg_cost` weighted averages and float subtraction can leave `0.30000000000000004 - 0.3` (about 5e-17, under the 1e-6 threshold, so the row is deleted, which is correct). A `<` vs `<=` slip or skipping the 4 dp rounding after subtraction leaves ghost positions.

**How to avoid:**
- Decide once and document it: round the fill price to 2 dp at the moment of fill (and store that in `trades.price`), then `cost = Decimal(price) * Decimal(qty)` quantized to cents with `ROUND_HALF_UP`. Use `Decimal` (built from `str()` of floats) inside the trade function, and store REAL.
- Round the new quantity to 4 dp after every add or subtract. Round `avg_cost` to a fixed precision (4 dp is safer than 2 dp, so repeated averaging does not drift). Display it at 2 dp.
- Compare against cash using the cent-rounded cost, not the raw product.
- Unit tests for the spec edge cases: buy with exactly all cash, a sell of the whole position, 3 buys of 0.1 shares then sell 0.3, quantity `0.00004` (rounds to 0, `INVALID_QUANTITY`), `qty=0`, negative, and NaN/Infinity/string quantities. Pydantic must reject these before they reach the function, with the `{error, code}` shape.
- The frontend must recompute live values with the same rounding rules. Otherwise the header total shows a 1-cent flicker against the server value after each trade.

**Warning signs:**
Totals off by $0.01, `-0.0` displayed, positions with quantity `1e-17`.

**Phase to address:** P1 (backend), P3 (frontend calc parity, pure-logic unit tests).

---

### Pitfall 6: FastAPI error shape leaks: 422 validation errors, `HTTPException`, and unknown `/api/*` paths do not use `{error, code}`

**What goes wrong:**
- FastAPI returns `{"detail": [...]}` with 422 for a bad body (missing `side`, string quantity). The spec requires `{error, code}` with 400 and the specific code.
- `HTTPException(detail=...)` produces `{"detail": ...}`.
- `MarketDataError` (with `http_status`/`code`) has no handler yet (CONCERNS.md).
- A request to an unknown `/api/foo` falls through to the `StaticFiles` mount at `/` and returns an HTML 404 (or `index.html`). The frontend then fails JSON parsing on an error path.
- Side not in `{buy, sell}` must give a defined code. The spec has no `INVALID_SIDE` code, so decide and document (likely 400 `INVALID_QUANTITY`-adjacent or a new documented code; do not invent silently).

**How to avoid:**
- Register handlers for `RequestValidationError`, `StarletteHTTPException` and the domain exception base. Map all of them to `{error, code}`.
- Register an `/api/{path:path}` catch-all returning JSON 404 before the static mount.
- Contract tests iterate every route's failure modes and assert the exact shape and status.
- Validate and normalize the ticker through `normalize_ticker` at every entry point: trade, watchlist add, chat actions. Chat actions get invalid tickers from the LLM, so they matter most.

**Warning signs:**
Any response with a `detail` key. The frontend "Unexpected token <" JSON error.

**Phase to address:** P1.

---

### Pitfall 7: SSE through FastAPI/uvicorn (buffering, disconnect detection, shutdown hang, reconnect)

**What goes wrong:**
- Middleware buffers the stream. `GZipMiddleware` and other `BaseHTTPMiddleware` implementations can buffer or break streaming responses. Do not add gzip to the app.
- Missing headers: use `media_type="text/event-stream"`, `Cache-Control: no-cache` and `X-Accel-Buffering: no` (harmless without a proxy, essential if a proxy is ever added).
- Zombie generators: if disconnect is only checked once per loop with `request.is_disconnected()`, a stalled client can keep a generator alive. Catch `asyncio.CancelledError` in the generator and always release resources in `finally`.
- Shutdown hang: uvicorn waits for open streaming connections on graceful shutdown. `docker stop` waits 10 s and then SIGKILLs, and `stop_*` scripts feel broken (and Ctrl+C in local dev hangs). Set `--timeout-graceful-shutdown 2` (or similar) and make the generator end quickly when the app is shutting down (a shutdown event flag checked each tick).
- EventSource semantics: it auto-reconnects only after network errors. If the server answers with a non-200 status or a wrong `Content-Type`, the state goes to `CLOSED` permanently and the dot goes red forever. Hence a 500 on the stream endpoint during startup (cache not ready) is fatal for the client. Return 200 and stay open from the first request.
- Browser limit: about 6 HTTP/1.1 connections per origin. Several tabs, or Playwright tests that leave stale pages open, can starve the `fetch` calls.
- The idle comment keepalive (`: ping\n\n`) every ~15 s keeps intermediaries from closing the connection. Add it; the existing `stream.py` has some keepalive, so verify it.
- Existing `stream.py` notes: polling every 0.5 s adds up to 500 ms latency, and `first` only flips on non-empty. Acceptable, but a test should cover "connect to an empty cache".
- The dot semantics: `OPEN` means connected, but if the Massive poller dies (401) the stream is open and silent while the dot stays green. Consider exposing poller health through `/api/health` (extra fields are allowed alongside `{"status": "ok"}`; keep `status` first and unchanged).
- Windows: `uvicorn --reload` with multiple tasks sometimes leaves orphan processes holding port 8000. Do not use `--reload` in the container.

**How to avoid:**
Dedicated SSE tests with `httpx.AsyncClient` streaming (first event contains all tickers, later events only deltas, a client disconnect releases the generator). A manual `docker stop` timing check of under 3 s in P4.

**Warning signs:**
Prices arrive in bursts, stop after N seconds, the container takes 10 s to stop, the dot is red after a backend restart and never recovers.

**Phase to address:** P1 (stream wiring and shutdown), P3 (EventSource handling), P4 (stop timing).

---

### Pitfall 8: Priced-ticker set drifts out of sync (NO_PRICE on sells, stale prices, reset leaves orphans)

**What goes wrong:**
PLAN: priced set = watchlist ∪ open positions. Nothing calls `sync_priced_tickers` yet. If any mutation path forgets it (watchlist remove, a sell that closes a position, chat actions, reset, startup), a held ticker loses its price and the sell fails with `NO_PRICE`. Or removed tickers keep ticking forever. After `POST /api/reset`, positions for non-default tickers must stop being priced, and the default watchlist must be priced again.

**How to avoid:**
- Call `sync_priced_tickers` from one place, a single service function (`after_mutation()`), used by watchlist add/remove, trade execution, chat executor, reset and lifespan startup.
- Startup order in lifespan: init DB, seed, build the data source, load priced tickers, start the task, start the snapshot task. The reverse order at shutdown.
- Test the sequence: hold TSLA, remove it from the watchlist, confirm it is still priced, sell, and confirm it is unpriced.
- Massive-mode `add_ticker` can block a request for up to 10 s (CONCERNS.md). Do not call it while holding the trade lock. Cap or document it, or the whole trading path stalls on a slow API.
- The watchlist add path validates in Massive mode (`UNKNOWN_TICKER`) but the current implementation accepts tickers leniently during outages. A DB watchlist entry may have null prices; the API must return null fields (`EMPTY_PRICE_FIELDS`).

**Warning signs:**
`NO_PRICE` for a ticker the user just held. SSE keys disappearing from the stream.

**Phase to address:** P1.

---

### Pitfall 9: `StaticFiles(html=True)` at `/` and Next.js `output: 'export'` mismatches

**What goes wrong:**
- The mount must be registered after all `/api` routes (the spec says so), but an unknown `/api/*` path then returns HTML (see Pitfall 6).
- `StaticFiles` raises `RuntimeError` at startup if the `static/` directory does not exist. Local dev (no frontend build) and the pytest `TestClient` app creation both crash. Mount only when the directory exists, or create it in the test fixture.
- `html=True` maps `/dir/` to `dir/index.html`, but `/page` does not map to `page.html`. The default Next export (`trailingSlash: false`) emits `page.html`. For this single-page app only `/` matters, but a hand-typed `/chart` shows a 404. Set `trailingSlash: true` only if more routes are added. Keep to one route.
- `next export` constraints: no API routes, no `rewrites`/`redirects`/`headers` at runtime, no server components that fetch at request time, no `next/image` optimization (set `images: { unoptimized: true }`), and `useSearchParams` needs a `Suspense` boundary or the build fails. `next dev` with `output: 'export'` cannot proxy `/api` to port 8000. For local frontend development either run the built export behind FastAPI, or use an env-driven API base (`NEXT_PUBLIC_API_BASE`, default `""` for same origin). `rewrites()` in the config only works in `next dev` and prints a warning on build (verify for the Next version in use).
- The static output dir is `out/`. The Dockerfile must copy `frontend/out` and not `.next`.
- Browser-only APIs (`EventSource`, `window`, `localStorage`) in module scope or in the render path break the build (prerender in Node). Use `"use client"` plus `useEffect`.
- Cached assets and `index.html` after a rebuild: hashed assets are fine, but Playwright re-uses nothing, so this is minor.

**How to avoid:**
Build the export in P3 and have a backend test that serves it (or a stub dir) and asserts `GET /` returns 200 HTML, `GET /api/health` returns JSON, and `GET /api/nope` returns a JSON 404.

**Warning signs:**
`RuntimeError: Directory 'static' does not exist` in tests. HTML returned for an API call.

**Phase to address:** P1 (conditional mount + API catch-all), P3 (export config), P4 (Dockerfile copy path).

---

### Pitfall 10: Recharts under static export (SSR, ResponsiveContainer, Treemap, animations, flakiness)

**What goes wrong:**
- `ResponsiveContainer` measures its parent. Rendered during prerender, or inside a parent with no explicit height, it renders at width/height 0 and logs "width(0) and height(0)" warnings. Give every chart parent a definite height (`h-full` in a flex layout with `min-h-0`, or a fixed px height). Mark chart components `"use client"` and, if hydration warnings occur, render them only after mount.
- Treemap custom `content`. The renderer receives `x, y, width, height, depth, name, root` and the data fields. For the heatmap you need `data-pnl` on each rectangle and the colour computed from `pnl_percent` (clamp ±10%). Treemap also draws a root/parent node (depth 0) through the same content callback, so guard with `depth` (or check for your own fields) or you get an extra rectangle and a wrong count in tests. Zero or negative `value` entries break the layout (a position with market value 0). An empty `data` array renders nothing, so show an explicit empty state.
- Animations. The default `isAnimationActive` animates in over ~1.5 s and re-animates on every data change. With data updates every 500 ms this causes constant re-animation, jank, and Playwright assertions on fill or `data-pnl` reading mid-transition values. Set `isAnimationActive={false}` on all Line/Area/Treemap charts and sparklines.
- Rendering cost. 10 sparklines re-rendering at 2 Hz with growing arrays is fine only if history is capped (for example 200 to 300 points per ticker) and the arrays are not re-created for charts whose ticker did not change. The unbounded price history in a long-lived tab leaks memory. Use a ring buffer.
- Mixed X axis types. Use numeric epoch ms with `type="number" domain={['dataMin','dataMax']}` for time series, and format ticks.
- Y axis `domain={['auto','auto']}` on a sparkline flattens tiny moves into a straight line. Use `['dataMin','dataMax']`.
- P&L chart with one snapshot point renders nothing visible (a single point line). Seed an initial snapshot at startup or show the dot.
- Recharts 3.x vs 2.x differences exist (verify the installed version and its Treemap/`content` signature; ensure React version compatibility).

**How to avoid:**
Pure functions for colour scale and geometry, unit tested. Add stable `data-testid`s (`heatmap-cell-AAPL`, `pnl-chart`). Assert E2E on `data-pnl` and presence of SVG paths, not on exact pixels.

**Warning signs:**
Console warnings about chart size, an extra cell in the heatmap, animations visible every tick.

**Phase to address:** P3. Flag the Treemap/heatmap plan for a short spike.

---

### Pitfall 11: Flaky E2E from live prices, timing, and test isolation

**What goes wrong:**
- Assertions on exact prices. The simulator is random, so only assert shape and change (for example "price text changed within 5 s", "is a number > 0"). Never compare to a literal price.
- `POST /api/reset` per test is mandated, but the app is stateful and the SSE connection from a previous test's page may still be open. Reset clears positions, but the in-memory price cache and `open_price` persist, so `change_percent` is not deterministic across tests. Also, reset must re-sync the priced set (Pitfall 8) and must not wipe the price cache for default tickers.
- Race with the 30 s snapshot task. P&L chart "has data points" can pass or fail depending on timing. Rely on the immediate post-trade snapshot (spec) and a snapshot at startup, and assert after a trade.
- Position quantity maths in E2E: after "buy 1 AAPL" the cash is `10000 - price`, a moving target. Assert cash decreased and the position row exists, or read the trade price from the API response.
- `waitForTimeout` sleeps instead of web-first assertions (`expect(locator).toHaveText`, auto-retry). Make the dot, the price cells and the chat messages addressable by `data-testid`.
- Parallel workers share one app and one DB. Run with `workers: 1` (or one app container per worker), otherwise resets in one test destroy another test's state.
- Compose startup race. `depends_on` without a health condition only waits for container start. Give the app a `healthcheck` (`/api/health`; the slim Python image has no `curl`, so use `python -c "import urllib.request..."` or install curl) and use `depends_on: condition: service_healthy`. Also wait for the first SSE event, not only health. Add a global setup that polls the stream endpoint.
- Base URL. Inside the compose network the app is `http://app:8000`, not `localhost`. Pass `BASE_URL` via env and use `baseURL` in the Playwright config. A hard-coded `localhost:8000` fails inside the Playwright container.
- Playwright image version must match the `@playwright/test` npm version exactly (`mcr.microsoft.com/playwright:vX.Y.Z-jammy`), otherwise browsers are not found.
- Test results and traces from a container need a mounted volume to be readable on the host. On Windows, use named volumes or a bind-mount of the project path, and check the path syntax.
- The "SSE resilience: after a page reload the dot returns to green" scenario should assert with a generous timeout and also that the price changes again, not only that the dot is green.
- LLM mock mode must be enabled in the test compose (`LLM_MOCK=true`) and must not need `OPENROUTER_API_KEY`. The mock regex ("first match wins") must be tested: "buy 1 AAPL" does not accidentally match `add` or `watch`, and `buy 10 AAPL` does not need the TICKER to be in the watchlist.

**Phase to address:** P5 (plus testids and mock mode contract in P2/P3).

---

### Pitfall 12: Windows host issues: CRLF in shell scripts, line endings in the image, volumes, PowerShell idempotency

**What goes wrong:**
- `git` on Windows with `core.autocrlf=true` converts `.sh` files (and any `entrypoint` script, `Dockerfile` heredocs) to CRLF. Inside the Linux container: `/bin/sh^M: bad interpreter` or `exec format error`. The same breaks `start_mac.sh` for macOS-using students who clone on Windows.
- Add `.gitattributes`: `*.sh text eol=lf`, `Dockerfile text eol=lf`, `*.yml text eol=lf`. Apply this before the first script is committed, since renormalising later needs `git add --renormalize .`.
- The `.env` file: Windows editors may save it with CRLF or a BOM. With `docker run --env-file` a trailing `\r` ends up in the value (`OPENROUTER_API_KEY=abc\r`, auth fails mysteriously, and `MASSIVE_API_KEY=\r` makes the key look "non-empty", which wrongly selects Massive mode). Strip whitespace in the settings loader (`.strip()`), treat whitespace-only as empty, and `.env.example` is committed with LF. A `docker --env-file` also does not strip quotes: `KEY="value"` keeps the quotes. Document no quotes.
- Named volume vs bind mount: stay with the named volume `finally-data:/app/db` as the spec says. A bind mount from a Windows path makes SQLite WAL fail or run slowly (WAL needs shared memory, unreliable over the Windows file share). Never mount `./db` into the container.
- The volume is created root-owned. If the Dockerfile later switches to a non-root user, the DB dir is not writable. Either stay root (simplest, document it) or `chown` the `/app/db` directory in the image before declaring the volume so the volume inherits ownership.
- An application default path: the spec has the DB at `db/finally.db` locally and `/app/db` in Docker. Resolve the path relative to the project root with an env override (`DB_PATH`), not relative to the CWD, so `uv run` from `backend/` and from the root hit the same file. Create the parent directory on startup.
- PowerShell scripts. Execution policy blocks unsigned `.ps1` files by default. Tell users to run `powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1` and use that form in docs. Idempotency pitfalls: `docker rm -f` of a missing container writes an error (use `docker rm -f name 2>$null` or check `docker ps -a --filter name=`); `$ErrorActionPreference = 'Stop'` does not trip on native command failures (check `$LASTEXITCODE` after each `docker` call); a stale container named `finally` blocks `docker run` (remove before run); the image build should be skipped when it exists unless `-Build`; the script must verify Docker Desktop is running (`docker info`) and print a friendly message.
- Use `Start-Process "http://localhost:8000"` for browser open, only after polling `/api/health` (not immediately).
- The script's `.env` check: if `.env` is missing, copy from `.env.example` (and warn about the missing key), instead of failing with a Docker error.
- Line endings in Python or TS files are not a problem; but a Windows-only path in a Dockerfile `COPY` (backslashes) is.
- Bind to `127.0.0.1` in the `docker run -p 127.0.0.1:8000:8000` form (CONCERNS.md security note). `uvicorn` inside the container must listen on `0.0.0.0`, not the default `127.0.0.1`. Otherwise the published port resets connections even though the container is "running". This is the most common "it works locally and not in Docker" failure.
- Docker Desktop on Windows: first build is slow (the npm install and uv sync), so add `.dockerignore` (`node_modules`, `.next`, `out`, `.venv`, `__pycache__`, `.git`, `db/*.db`, `.env`). Without it the Windows host's `node_modules` (Windows binaries, for example `@next/swc-win32`) gets copied into the Linux build context and `COPY` overwrites the Linux install.

**Phase to address:** P4 (and `.gitattributes` in P0, before any script is written).

---

### Pitfall 13: Docker multi-stage and uv build mistakes

**What goes wrong:**
- `uv sync` without `--frozen`/`--locked` re-resolves in the image and drifts from the tested lockfile.
- The project has `[tool.uv] package = false` (virtual project). Do not `COPY` only `pyproject.toml` and then run `uv sync --no-install-project` expecting the app to install. The app runs from source with `PYTHONPATH`/working directory `backend/`. Verify that `uvicorn app.main:app` imports from the `WORKDIR`.
- The venv path. Running `uv run uvicorn` at container start re-syncs (a network call, may fail offline). Use `.venv/bin/uvicorn` directly or `uv run --no-sync`, with `UV_COMPILE_BYTECODE=1`.
- Static dir location: the code mounts `static/` relative to somewhere. Compute from `Path(__file__)` and match the Dockerfile `COPY --from=frontend /app/out /app/static` target.
- `tzdata` is needed in the slim image too (`zoneinfo` has no system tz database there; keep the `tzdata` Python package).
- One worker only (module-level cache and simulator, CONCERNS.md). Never pass `--workers N`.
- A `HEALTHCHECK` in the Dockerfile for `docker ps` health, using Python since there is no curl.
- The `.env` is read "from the project root" by the backend (spec), but the container gets variables through `--env-file`. The loader must not fail when `.env` is absent in the container. Use `python-dotenv` with `override=False` so real env vars win.
- Logging: set `PYTHONUNBUFFERED=1` or log lines never appear in `docker logs` until exit.

**Phase to address:** P4.

---

## Moderate Pitfalls

### Pitfall 14: Chat flow correctness (one LLM call, order of operations, history)

**What goes wrong:**
- Trades are executed in the order given; a buy that funds a later one cannot work in reverse, but a sell followed by a buy in one message needs the order preserved. Do not run actions concurrently via `gather`; run sequentially under the shared lock (take the lock per trade, not around the whole LLM call, or all manual trades stall for the length of the LLM latency).
- The LLM's `quantity` may arrive as a string, negative, or a huge number; validate through the same Pydantic/trade function, and let failures become `status: "error"` actions, never exceptions.
- Duplicated or hallucinated tickers (`"Apple"`, `"aapl "`, `"$AAPL"`). Normalise, and report invalid ones as `INVALID_TICKER` action errors.
- History of 20 messages includes stored `actions` JSON. Serialise those into the prompt compactly (for example a one-line summary per action) so the context does not bloat, and ensure the history order is chronological (query `ORDER BY created_at DESC LIMIT 20`, then reverse). Use a monotonic tie-break (`rowid`) because two messages can share a timestamp.
- Persist the user message and the assistant message only after the response is built; if the LLM call fails, decide whether to store the user message (recommended: store both, with the apology), so history stays coherent.
- The prompt must include live prices from the cache at request time, not stale values.
- Prompt injection from ticker names or earlier chat is low-risk here (fake money), but the LLM must not be able to call anything except trades/watchlist, which holds by construction.
- Missing key: `LLM_MOCK != true` and no key must return 200 with the exact spec message and an empty `actions` list. Test it.
- The mock pattern order. First match wins in the spec's table order. Case-insensitive; `buy 10 aapl` yields `AAPL`; fractional quantities (`buy 0.5 AAPL`) must parse. A regex like `buy (\d+) ([A-Z]+)` with `re.I` would capture `10` and `aapl`. Normalise afterwards. Also `\d+(\.\d+)?`.

**Phase to address:** P2.

### Pitfall 15: Reset semantics

**What goes wrong:**
`POST /api/reset` must clear positions, trades, snapshots and chat messages, restore cash and the default watchlist, and return the portfolio. Pitfalls: forgetting to take the lock, forgetting the priced-set re-sync, leaving the snapshot task writing a pre-reset total after the reset, and not inserting a fresh initial snapshot (empty P&L chart). A frontend that does not refetch the watchlist, history and chat after reset shows stale state.

**Phase to address:** P1 (backend), P3 (frontend refetch).

### Pitfall 16: Frontend live-value math and render churn

**What goes wrong:**
- Recomputing everything on each SSE event (2 Hz × 10 tickers) re-renders the whole tree. Keep prices in a store with per-ticker subscriptions (for example Zustand selectors, or `useSyncExternalStore`), and memoise derived values.
- Price flash: if the flash class is added by a state change and removed with `setTimeout`, rapid ticks stack timers and leave the class stuck or never retrigger (the class is already present, so no transition restarts). Use a key-based re-mount or toggle off then on with `requestAnimationFrame`, and clear the timer on unmount. A "flat" direction should not flash.
- Holding the SSE parse in a component that re-mounts (React strict mode double-effect in dev) opens two connections. Create the `EventSource` once at module or provider level and close it in cleanup.
- Merging deltas: an event contains only changed tickers. Replacing the whole price map with each event drops unchanged tickers (relevant in Massive mode).
- The initial portfolio fetch vs the first SSE event race: render a loading state and compute `current_price` with a fallback to `avg_cost` (as the spec says).
- Timestamps: the SSE `timestamp` is server time. Use it for chart X, not `Date.now()`, otherwise reconnect gaps look wrong. Be careful about `new Date("2026-10-12T14:03:21.512Z")` parsing (fine) vs strings without `Z`.
- Reconnect: after reconnect the first event is a full snapshot. Do not append a duplicate point per ticker with the same timestamp.
- A sparkline needs at least two points; handle one.
- Trade error text from `{error, code}` shown next to the trade bar must clear on the next successful action.

**Phase to address:** P3.

### Pitfall 17: The Massive path and simulator corner cases

**What goes wrong:**
Documented in CONCERNS.md: the poller can die permanently on a 401 while the dot stays green, and the free tier gets static end-of-day prices (deviation from the spec's 15 s poll, undocumented). `MASSIVE_POLL_INTERVAL` is an undocumented env var. Time-dependent EOD logic has no holiday calendar. These matter little to the default simulator path, so do not let them consume phase time. Mitigation: surface poller state through `/api/health`, document the deviation in a planning note (do not edit locked PLAN.md without the user), and keep E2E on the simulator.
- Removing and re-adding a simulator ticker resets `open_price` (daily change goes to 0). Accepted; note it in the test expectations.

**Phase to address:** P1 (health field, optional), later (hardening).

### Pitfall 18: Snapshot task lifecycle

**What goes wrong:**
A background `asyncio.create_task` that raises is silently dropped, so snapshots stop and nobody notices. Wrap the loop body in `try/except Exception` with logging and keep looping. Cancel both tasks on shutdown and `await` them (with `suppress(CancelledError)`). Keep references to tasks (the loop only holds weak references, so they can be garbage-collected). Use a startup snapshot immediately so the P&L chart has a first point. A 30 s cadence with a long-running tab produces thousands of rows per day; the history endpoint should not return unbounded data (downsample or limit, without changing the response shape).

**Phase to address:** P1.

### Pitfall 19: Tests that do not exercise the real app wiring

**What goes wrong:**
`TestClient(app)` without `with` does not run the lifespan, so the DB is never initialised and the market task never starts; the tests either fail confusingly or test a different app than production. Use `with TestClient(app)` or `httpx.ASGITransport` plus `LifespanManager`. Tests must use a temp DB path (env-injected) and must never touch `db/finally.db`. The module-level singletons (cache, lock) leak between tests; build them in lifespan and store them on `app.state`. An `asyncio.Lock` created at import time under a different event loop raises "attached to a different loop" on older Pythons (on 3.12 it binds lazily, still avoid import-time creation).
Use the `pytest-asyncio` mode consistently (`asyncio_mode = "auto"` in `pyproject.toml`).

**Phase to address:** P1.

---

## Minor Pitfalls

### Pitfall 20: Small spec-conformance traps

- `DELETE /api/watchlist/{ticker}` returns 204 with an empty body. A FastAPI route with `status_code=204` must return `Response(status_code=204)` (a JSON `null` body with 204 triggers h11 errors in some versions). Verify.
- Lower-case path ticker must normalise before lookup. `POST /api/watchlist` is idempotent and returns 200 (not 201).
- Rounding in JSON responses: money 2 dp, quantities 4 dp, `pnl_percent` 2 dp; make one serializer, not scattered `round()` calls.
- `change_percent` when `open_price` is 0 or missing: guard the division.
- `direction` compares `price` with `previous_price`; on first update `previous_price == price`, giving `flat`.
- The portfolio `current_price` fallback to `avg_cost` when not priced.
- Timestamps: ISO 8601 UTC with `Z`. `datetime.utcnow()` is deprecated; use `datetime.now(timezone.utc)`.
- UUID primary keys as TEXT: generate in Python (`str(uuid4())`).
- Leave `Connection: keep-alive` header off the SSE response (invalid under HTTP/2, noted in CONCERNS.md).
- Tailwind v4 vs v3 config differences (CSS-first config in v4): pick the version the scaffold gives and do not mix guidance. Custom colours (`#ecad0a`, `#209dd7`, `#753991`) go in the theme.
- Next.js `output: 'export'` still runs ESLint/TypeScript checks at build, so a type error fails the Docker build late. Run `npm run build` locally in P3 before relying on the Dockerfile.
- Fonts: `next/font/google` downloads at build; fails offline Docker builds. Prefer a system font stack or a local font.
- `localhost` vs `127.0.0.1` in Playwright on Node 18+ (IPv6 `::1` resolution) can cause connection refused. Use the compose service name.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Float arithmetic for cash and cost | Simple code | Off-by-a-cent failures, flaky equality tests | Never; use Decimal inside the trade function |
| Sync `sqlite3` called directly in async routes | No new dependency | Event loop stalls, SSE hiccups | Never beyond trivial startup code |
| Hard-coding the model/provider string in call sites | Fast to write | Provider change means edits in several places (already needed, Pitfall 1) | Never; single constant plus env override |
| Skipping the CI job "for now" | Saves 10 minutes | Conflict markers already reached history | Never |
| Using `time.sleep`/`waitForTimeout` in E2E | Quick green | Flaky suite | Never |
| Storing price history on the server | Page reload keeps sparklines | Contradicts spec (no price-history endpoint) | Never (spec) |
| One giant `main.py` | Speed | Untestable wiring | Only for the very first skeleton; split by P1 end |
| Mock LLM only by flag at the route | Easy | Real parsing path never tested | Acceptable if the parser/executor is tested separately with canned raw strings |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenRouter via LiteLLM | Model string without the `openrouter/` prefix. LiteLLM then fails to route or picks another provider (verify exact form in the skill smoke test) | Use the form the smoke test proves; keep the provider `order` as a hint only |
| OpenRouter provider routing | Assuming `order: ["cerebras"]` guarantees Cerebras | Check the `provider` field in the response; Cerebras does not serve this model today |
| OpenRouter free models | No handling of 429 and daily caps | Retry once, then friendly message; E2E uses `LLM_MOCK` |
| LiteLLM structured output | Trusting `response_format` to be enforced | Tolerant parse plus Pydantic validation, schema also in the prompt |
| LiteLLM sync API | `completion()` inside `async def` | `acompletion()` |
| Massive/Polygon | Logging request headers, or assuming the free tier gives live ticks | Never log headers; accept EOD behaviour on the free plan |
| Docker `--env-file` | Quotes and CRLF kept in values | No quotes in `.env.example`; strip in the loader |
| Playwright in compose | `localhost` base URL, version mismatch, no health wait | Service-name base URL, pinned matching image, `service_healthy` |
| Recharts in Next export | Charts measured at SSR | `"use client"`, fixed-height parent, animations off |
| EventSource | Treating `CLOSED` as retrying | On `CLOSED`, show red; consider a manual re-create with backoff since the browser will not retry after an HTTP error response |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded client price history | Memory growth, chart slowdown | Ring buffer, 200 to 300 points per ticker | Hours-long session |
| Re-rendering every panel on each SSE tick | Choppy flashes, high CPU | Per-ticker selectors, memoised derived data | 10+ tickers at 2 Hz |
| Chart animation on every update | Constant motion, flaky tests | `isAnimationActive={false}` | Immediately |
| Unbounded `portfolio_snapshots` read | Slow history call, huge P&L chart | Limit or downsample | Days of uptime (2880 rows per day) |
| Per-client JSON encoding in `stream.py` | CPU per tab | Fine for one user; note only | More than a few tabs |
| Blocking Massive `add_ticker` (up to 10 s) | Watchlist add hangs the UI | Do not hold locks while waiting; show a pending state | Slow/limited API |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Publishing 8000 on all interfaces | Anyone on the LAN can trade, reset and spend the OpenRouter key | `-p 127.0.0.1:8000:8000` in scripts (container still binds 0.0.0.0) |
| Committing `.env` or baking it into the image | Key leak | `.gitignore`, `.dockerignore`, pass at run time only |
| Logging full LiteLLM exceptions or request kwargs | API key in logs | Log type and short message only |
| LLM-supplied values trusted | Invalid or absurd trades | Same validation path as manual trades |
| `POST /api/reset` unauthenticated | Data loss on a shared host | Accepted by spec; keep localhost binding |
| `.claude/` and GitHub workflow secrets | Third-party action permissions (CONCERNS.md) | Review before enabling; out of scope for this build |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Blank panels before the first SSE event or first fetch | First launch looks broken, which is the whole demo | Skeletons, and the full snapshot on connect fills at once |
| Silent chat failure | User thinks the AI ignored them | Always show an assistant bubble, including for errors and missing key |
| Trade error far from the trade bar | Missed feedback | Inline next to the bar (spec), cleared on success |
| Flash colours too strong or persistent | Garish, hurts the "Bloomberg" look | About 500 ms fade, low-alpha background |
| Heatmap with one position looks like a single block | Underwhelming | Fine, but keep an empty state with a hint; for demos the AI can buy several tickers |
| Treemap gray vs red/green with no legend | Unclear | Small legend or tooltip with ticker, weight and P&L% |
| Chat panel scroll jumping | Annoying | Scroll to bottom only when the user is at the bottom |
| Dot yellow forever after backend restart | Looks broken | Handle `CLOSED` with a retry |

## "Looks Done But Isn't" Checklist

- [ ] **Market module:** `uv run pytest` green and no `<<<<<<<` anywhere, including `uv.lock` and `pyproject.toml`.
- [ ] **Trades:** concurrent trades test passes, the post-trade snapshot is written, and rounding edge cases are covered.
- [ ] **Errors:** every endpoint's failures return `{error, code}`, including 422 cases and unknown `/api/*` paths.
- [ ] **SSE:** works through the built Docker image (not only `uv run`), and `docker stop` completes in a few seconds.
- [ ] **Chat:** real model smoke run done once with the actual key, including a malformed-JSON fallback test and the no-key message.
- [ ] **Chat actions:** a failed action does not stop later ones, and the result appears inline.
- [ ] **Static export:** `npm run build` produces `out/index.html`, the Docker image serves it at `/`, and the API still works.
- [ ] **Heatmap:** `data-pnl` on each rectangle, no extra root rectangle, colour clamps at ±10%.
- [ ] **P&L chart:** has points on a fresh start (startup snapshot exists).
- [ ] **Reset:** E2E isolation actually works (positions, cash, watchlist, chat cleared; priced set re-synced).
- [ ] **Scripts:** run twice in a row on Windows with no errors, work with Docker stopped (friendly message), and open the browser only after health is OK.
- [ ] **Line endings:** `.gitattributes` in place, and a fresh clone with autocrlf on still builds.
- [ ] **E2E:** runs from a cold `docker compose -f test/docker-compose.test.yml up --build --exit-code-from playwright` and passes three times in a row.
- [ ] **Persistence:** stop and start the container; the data survives in the named volume. A fresh volume seeds the defaults.
- [ ] **README Quick Start:** matches reality (scripts and `.env.example` exist).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Provider/structured output not working (1) | LOW | Env-override the model, switch to the tolerant parser, optionally switch to a model with a real structured-output endpoint (a decision for the user, since it touches the spec) |
| Conflict markers recur (2) | LOW | Add the grep guard, re-resolve |
| Event loop stalls (3) | MEDIUM | Wrap DB calls in a repository layer with `to_thread` or aiosqlite |
| Half-applied trades or negative cash (4, 5) | MEDIUM | Funnel everything through the one trade function, add the invariant test (`cash + cost basis = 10000 + realised flows`), reset |
| CRLF-broken scripts (12) | LOW | Add `.gitattributes`, `git add --renormalize .`, rebuild |
| SQLite WAL failure on a bind mount | LOW | Switch to the named volume, or set `journal_mode=DELETE` |
| Flaky E2E (11) | MEDIUM | Replace sleeps with web-first assertions, testids, `workers: 1`, health gating |
| Recharts layout bugs (10) | LOW | Fixed-height parents, animations off, guard `depth` in the Treemap content |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 LLM provider/model reality | P2 (research flag) | Live smoke script logs serving provider; tolerant-parser tests with fenced and prose output |
| 2 Conflict markers, no CI | P0 | Grep guard test, `uv run pytest` green in CI |
| 3 Blocking the event loop | P1, P2 | Test: SSE ticks continue during a slow mocked LLM call and a DB write |
| 4 Transaction/lock semantics | P1 | `asyncio.gather` double-buy test; rollback test |
| 5 Float money | P1, P3 | Edge-case unit tests; frontend calc parity tests |
| 6 Error shape | P1 | Contract test over all routes and failure modes |
| 7 SSE specifics | P1, P3, P4 | Streaming httpx test; `docker stop` timing; E2E reload test |
| 8 Priced-set sync | P1 | Hold-then-unwatch-then-sell test; reset test |
| 9 Static mount and export | P1, P3, P4 | Tests for `/`, `/api/health`, `/api/nope`; image smoke |
| 10 Recharts | P3 | Unit tests for colour scale; E2E on `data-pnl`; no console size warnings |
| 11 Flaky E2E | P5 | Three consecutive cold runs green |
| 12 Windows host issues | P0 (`.gitattributes`), P4 | Fresh clone build; scripts run twice |
| 13 Docker/uv build | P4 | Clean build from lockfile; container serves on the published port |
| 14 Chat flow | P2 | Mock-mode table tests; failed-action ordering test; no-key test |
| 15 Reset | P1, P3 | Reset API test; E2E isolation |
| 16 Frontend live math | P3 | Pure-logic unit tests; flash-class test |
| 17 Massive/simulator corners | P1 (health), later | Health field test; doc note |
| 18 Snapshot task | P1 | Test that an exception in one cycle does not kill the loop |
| 19 Test wiring | P1 | Tests run with lifespan and a temp DB |
| 20 Small spec traps | P1, P3 | Checklist review |

## Sources

- OpenRouter models API, checked live 2026-10-13: `https://openrouter.ai/api/v1/models` and `https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b/endpoints` (and the `:free` variant). HIGH confidence for the provider and supported-parameter findings. These can change at any time.
- `.claude/skills/cerebras/SKILL.md` (the project's own LLM call recipe: sync `completion`, `provider.order`).
- `.planning/codebase/CONCERNS.md`, `.planning/PROJECT.md`, `planning/PLAN.md` (project-internal; HIGH for project facts).
- Established knowledge of Starlette/uvicorn streaming and shutdown behaviour, WHATWG EventSource reconnection rules, Python `sqlite3` transaction control, SQLite WAL requirements, Next.js static export limits, Recharts `ResponsiveContainer`/`Treemap`/`isAnimationActive`, Playwright Docker image pinning, and Docker `--env-file` parsing. MEDIUM confidence; not re-verified against current docs in this pass. Items marked (verify) should be checked in the owning phase.

---
*Pitfalls research for: AI-powered trading workstation (FinAlly)*
*Researched: 2026-10-13*
