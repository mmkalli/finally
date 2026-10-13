# Project Research Summary

**Project:** FinAlly — AI Trading Workstation
**Domain:** Single-user simulated trading terminal with LLM copilot (FastAPI + SQLite + SSE, Next.js static export, single Docker container)
**Researched:** 2026-10-13
**Confidence:** MEDIUM-HIGH

## Executive Summary

FinAlly is a single-user, single-process, single-container trading demo. `planning/PLAN.md` is locked, so research decides *how*, not *what*. The established approach:
- one asyncio loop, one SQLite connection and one in-memory `PriceCache`;
- all mutation flows through one `execute_trade` function that holds a process-wide lock and runs a synchronous `BEGIN IMMEDIATE` transaction with no `await` inside;
- REST routers and the LLM chat executor are thin layers over the same portfolio and watchlist services;
- the frontend keeps a per-ticker price store fed by `EventSource` and recomputes portfolio values client-side.

The project is brownfield. Only `backend/app/market/` exists, and 9 of its modules contain merge-conflict markers, so `import app.market` fails. Repairing them is a hard gate. `pyproject.toml` and `factory.py` are already resolved but uncommitted. Everything else is built fresh on the market slice's conventions: stdlib sqlite3, injected dependencies, and `MarketDataError` carrying `code`/`http_status`.

Top risks:
1. The spec's LLM provider/model pairing does not exist on OpenRouter today (see Decisions for the User).
2. A blocking sync LiteLLM call would freeze SSE.
3. Float money drift would break the spec's exact assertions.
4. Some error paths escape the `{error, code}` shape: 422s, and unknown `/api/*` paths that fall through to the static mount.
5. First-launch polish: every panel needs an empty state, and the first snapshot must be seeded.

## Key Findings

### Recommended Stack

The stack is locked by the spec. Versions were verified on PyPI, npm and MCR on 2026-10-13.

**Core technologies:**
- **Backend:**
  - Python 3.12, FastAPI 0.143 and uvicorn 0.54. Run uvicorn with **exactly one worker**, and use `lifespan` rather than `on_event`.
  - stdlib sqlite3 configured with `check_same_thread=False`, `isolation_level=None`, explicit `BEGIN IMMEDIATE`, WAL, `foreign_keys=ON` and `busy_timeout`. No ORM and no aiosqlite.
  - litellm `>=1.105,<1.106`, used only through `acompletion` and imported lazily.
  - pydantic `>=2.14`.
  - python-dotenv with `override=False`.
- **Frontend:**
  - Next 16.4, React 19.3, TypeScript ~6.0.3 (not 7), Tailwind 4.3 (CSS-first `@theme`) and Recharts 3.10.
  - `output: 'export'` with `images.unoptimized` and no rewrites.
- **Docker:** a `node:20-slim` build stage, then `python:3.12-slim` with a pinned uv image and `uv sync --frozen --no-dev`.
- **E2E:** the Playwright image `v1.64.0-noble` must match npm `@playwright/test` 1.64.0 exactly.
- **Frontend unit tests:** vitest 5 and jsdom 30 need Node 22 or later, so run them on the host or in CI, not in the Node 20 build stage. Fallback: vitest 4.1 with jsdom 29. Pin `@types/node` to `^20`.

### Expected Features

**Must have (table stakes, as polish on spec features):**
- Price flash that can re-trigger, applied to the price cell only, with no flash on `flat`.
- Shared number formatting with tabular numerals.
- An empty or loading state on every panel: no `NaN` and no blank charts.
- A startup snapshot so the P&L chart is never empty.
- Trade bar that disables while a request is in flight, shows errors inline and confirms success in one line.
- Heatmap with `data-pnl` and colours clamped at ±10%.
- P&L chart with a $10,000 reference line.
- Chat with inline action cards, followed by a shared `refreshAll()`.
- Connection dot, with prices dimmed when the stream is not OPEN.

**Should have (polish):**
- Staged reveal of action chips, with the affected row highlighted.
- Prompt chips that are valid for the mock patterns.
- A UI reset button.
- Tooltips.

**Defer / anti-features:**
- Defer: restoring chat history (a spec gap), candlesticks and timeframes, customizable layout.
- Anti-features: confirmation dialogs, limit orders, realized P&L, token streaming and a price-history API.

### Architecture Approach

**Major components:**
1. **`market/*`** (exists): the single writer to `PriceCache`.
2. **`database/`**: schema, seed, init and reset.
3. **`portfolio/service`**: `execute_trade` acquires the lock itself and inserts the snapshot inside the transaction. Also `build_portfolio` and the 30 s `snapshot_loop`.
4. **`watchlist/service`**: calls `source.add_ticker` before the DB insert, because `sync()` swallows `UnknownTickerError`.
5. **`llm/*`**: schema, prompt, injectable client, mock matcher and `chat_turn`.
6. **`errors.py`**: one unified handler covering `AppError`, `MarketDataError`, `RequestValidationError` and HTTP exceptions.
7. **`api/*`**: thin routers. **`main.py`**: lifespan wiring, with shared state on `app.state`.
8. **Frontend `lib/`**: a ring-buffer price store, per-ticker selectors, and pure `portfolio.ts` and `heatmap.ts`.

**Rules:**
- Mount static files last, only if `STATIC_DIR` exists, and register a JSON 404 for `/api/{path:path}` before the mount.
- Call `after_mutation()` → `sync_priced_tickers` after every watchlist, trade, chat or reset mutation, once the lock is released.
- Reset runs under the lock, re-syncs and inserts a baseline snapshot.
- Load dotenv before `create_market_data_source`.
- Use a `DB_PATH` env var.

### Critical Pitfalls

1. **The spec's LLM provider/model pairing does not exist.** Don't rely on enforced schemas. Prevention:
   - Put the schema and an example in the prompt.
   - Parse tolerantly (strip fences, take the first `{...}`), then validate with Pydantic.
   - Fall back to the raw text or an apology, with no actions.
   - Make the model an env-overridable `LLM_MODEL` constant.
   - Set `max_tokens`, a ~30 s timeout and at most 1 retry, and map every exception to a 200 chat response.
   - Add a live smoke script that logs which provider served the request.
2. **Conflict markers break the baseline.**
   - Resolve them per CONCERNS.md: `__init__.py` takes "theirs", `demo.py` takes HEAD, keep `tzdata`.
   - Then add a grep guard, run `uv lock`/`uv sync`, and get pytest green.
   - Add CI and `.gitattributes`, and remove the stale `__pycache__` dirs.
3. **Event-loop blocking.**
   - Use `acompletion`, keep DB work trivial, and never `await` inside a transaction.
   - Test that SSE keeps ticking during a slow mocked chat call.
4. **Atomicity and money.**
   - Use `Decimal` inside the trade function.
   - Round the fill price to 2 dp at fill and store that value. Quantize cost to cents.
   - Round quantity to 4 dp after every change, and keep `avg_cost` at 4 dp.
   - Test a concurrent double-buy and the edge cases: spend all cash, sell everything, 0.00004, NaN, Infinity.
5. **Error-shape leaks and priced-set drift.**
   - Return `{error, code}` for 422s, HTTP exceptions, domain errors and unknown `/api/*` paths.
   - Route every mutation through one `after_mutation()` resync.

**Later-phase traps:**
- **SSE shutdown hang:** use `--timeout-graceful-shutdown`, no `--reload`, no gzip.
- **Recharts:** give charts fixed-height parents, turn animations off, and guard Treemap `depth` so it doesn't render an extra root rect.
- **Flaky E2E:** `workers: 1`, healthcheck gating, a service-name base URL and web-first assertions.
- **Windows/Docker:** LF line endings in `.sh` files, a `.dockerignore`, bind `0.0.0.0` inside the container but publish on `127.0.0.1:8000`, named volume only, and idempotent PowerShell scripts that cope with Docker not running.

## Implications for Roadmap

Dependency chain: repair → backend core → chat and frontend in parallel → packaging → E2E. Services come before their consumers so that manual and LLM trades share one code path.

### Phase 1: Repair, Baseline and CI Guard (hard gate)
**Delivers:**
- Conflict markers resolved in the 9 market modules.
- Dependencies added via `uv add`, lockfile regenerated, market tests green.
- A marker-guard test and a minimal CI job.
- `.gitattributes`, `.dockerignore` and `.env.example`.
- Stale pycache directories removed.

**Avoids:** pitfall 2, CRLF.

### Phase 2: Backend Core
**Delivers:**
- `main.py` lifespan: DB init and seed, market source, 30 s snapshot task and baseline snapshot.
- `config.py` and `/api/health`.
- Stream router with a graceful-shutdown timeout.
- Conditional static mount, with a JSON 404 for unknown `/api/*` paths.
- Schema, seed and reset.
- `AppError` and the unified handlers.
- `execute_trade` and `build_portfolio`.
- Watchlist service and all REST routes, with `after_mutation()`.

**Tests:** real lifespan on a temp DB, concurrency, rollback, the full error matrix, hold→unwatch→sell, and reset.

### Phase 3: LLM Chat
**Delivers:**
- The mock matcher first, because E2E depends on it.
- Schema, prompt and history builder: last 20 messages, `rowid` tie-break, compact action summaries.
- `chat_turn` and `/api/chat`, including the exact no-key message.
- The `LLM_MODEL` override, the tolerant parser and a live smoke script.

### Phase 4: Frontend
Can start against SSE once the Phase 2 skeleton exists, and against REST once Phase 2 is done.

**Order:**
1. Scaffold, formatting, price store, `EventSource` and connection dot.
2. Watchlist with flash and sparklines, header, and `portfolio.ts`.
3. Trade bar, positions table and main chart.
4. Heatmap and P&L chart.
5. Chat panel with inline actions and `refreshAll()`, then polish.
6. Vitest pure-logic tests.

### Phase 5: Packaging
**Delivers:**
- Multi-stage Dockerfile: pinned uv, `--frozen`, `PYTHONUNBUFFERED`, a Python `HEALTHCHECK`, `0.0.0.0` bind, one worker, frontend build copied to `static`.
- PowerShell scripts first, then bash.
- Named volume, `127.0.0.1` publish, and whitespace stripping when reading `.env`.

**Checks:** `docker stop` finishes in under 3 s, scripts can be run twice, and data survives a restart.

### Phase 6: E2E
**Delivers:**
- Compose file with `service_healthy` gating.
- Playwright 1.64.0 pinned, `baseURL` set to the service name, `workers: 1`.
- `LLM_MOCK=true` and a reset before each test.
- Every test waits for the first SSE event.
- All PLAN.md §12 scenarios, asserting shape and change rather than literal prices.

**Exit gate:** 3 consecutive green runs from a cold start.

### Research Flags

**Need research:**
- Phase 3: OpenRouter routing and supported params, the LiteLLM `openrouter/` prefix, `extra_body` and `drop_params`.
- Phase 4: a short spike on Recharts 3 Treemap `content`/`depth`/`data-pnl`, plus the eslint and vitest version matrix.

**Standard patterns:** Phase 1 (guidance is in CONCERNS.md), Phase 2 (verify only sqlite3 transaction mode and the 204 response), Phases 5 and 6.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Versions are registry-verified; sqlite pragmas, Tailwind v4 and Next export details come from training knowledge |
| Features | MEDIUM | Spec plus trading-UI conventions; timings and caps are recommendations |
| Architecture | HIGH (backend) / MEDIUM (LiteLLM, frontend libs) | Derived from the existing source and PLAN.md |
| Pitfalls | MEDIUM-HIGH | OpenRouter findings were checked live; items marked "(verify)" still need checking |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **DB access:** use sync sqlite3, matching `priced.py`, with no `await` inside transactions. Revisit only if the SSE stall test fails.
- **Invalid `side` value:** the spec defines no error code for it. Decide and document one in Phase 2.
- **Fill price precision:** round to 2 dp at fill. Document this as an interpretation of the spec.
- **Chat storage when the key is missing or the call fails:** recommend storing both messages. Confirm in Phase 3.
- **Massive mode caveats:** the poller dies on a 401, the free tier only gives end-of-day prices, and `add_ticker` can block for up to 10 s. Keep E2E on the simulator and never hold the lock across `add_ticker`.

## Decisions for the User (research conflicts with the locked PLAN.md)

1. **LLM model and provider.** OpenRouter, checked live on 2026-10-13:
   - `nvidia/nemotron-3-ultra-550b-a55b:free` has a single endpoint, served by Nvidia. It does not support `response_format` or structured outputs.
   - Cerebras does not serve this model.
   - With `provider.order: ["cerebras"]`, requests silently route to Nvidia when fallbacks are allowed, and return 404 when they are not.

   Default: keep the spec model, make it env-overridable, and add the tolerant parser and smoke test.
2. **Chat history on reload.** The spec has no GET endpoint for chat. Default: chat is session-local in the UI, and the history is still loaded from the DB for the LLM.
3. **UI reset button.** The endpoint is in the spec, but no UI trigger is. Default: include it as polish.
4. **Node 20 build stage.** Node 20 is past end of life but still builds Next 16. Default: keep it.

## Sources

### Primary (HIGH confidence)
- OpenRouter models and endpoints API (live, 2026-10-13); PyPI, npm and the MCR tag list.
- `planning/PLAN.md`, `.planning/PROJECT.md`, `.planning/codebase/*`, `backend/app/market/*`.

### Secondary (MEDIUM confidence)
- The cerebras `SKILL.md` pattern.
- Established knowledge of Starlette/uvicorn, EventSource, sqlite3/WAL, Next export, Tailwind v4, Recharts, Playwright and Docker.

### Tertiary (LOW confidence)
- The `openrouter/` prefix and `drop_params` behaviour.
- eslint 10 with `eslint-config-next`.
- How far the ecosystem lags TypeScript 7.

---
*Research completed: 2026-10-13*
*Ready for roadmap: yes*
