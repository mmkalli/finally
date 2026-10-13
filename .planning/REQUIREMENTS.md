# Requirements: FinAlly — AI Trading Workstation

**Defined:** 2026-10-13
**Core Value:** One command launches a container where prices visibly stream, trades execute instantly, and the AI chat can place a trade that shows up inline.

**Contract:** `planning/PLAN.md` is binding. Requirements below reference its sections; where they restate it, PLAN.md wins on detail.

## v1 Requirements

### Foundation (repair & baseline)

- [ ] **FOUND-01**: All merge-conflict markers are resolved in `backend/app/market/` (per CONCERNS.md guidance) and `import app.market` succeeds
- [ ] **FOUND-02**: Backend dependencies (litellm, pydantic, python-dotenv, tzdata) are declared via uv and `uv.lock` is regenerated; `uv sync` succeeds
- [ ] **FOUND-03**: The existing market-data test suite passes (`uv run pytest`)
- [ ] **FOUND-04**: A guard test/CI check fails if any `^<<<<<<<` / `^>>>>>>>` conflict marker exists in the repo
- [ ] **FOUND-05**: Stale `__pycache__` dirs for `api/`, `chat/`, `database/`, `portfolio/` are removed
- [ ] **FOUND-06**: `.gitattributes` (LF for `.sh`, Dockerfile, `.yml`), `.dockerignore`, and `.env.example` exist

### App Shell

- [ ] **SHELL-01**: FastAPI app starts via lifespan: loads `.env`, initializes DB, starts the market data source, starts the 30s snapshot task, and shuts them down cleanly
- [ ] **SHELL-02**: `GET /api/health` returns `{"status": "ok"}`
- [ ] **SHELL-03**: `GET /api/stream/prices` is served by the app (existing stream router wired to `app.state.price_cache`)
- [ ] **SHELL-04**: Static frontend is mounted at `/` after all `/api` routes (only if the static dir exists); unknown `/api/*` paths return JSON 404, not `index.html`
- [ ] **SHELL-05**: Every error response — domain errors, validation (422), unknown routes — uses `{"error": ..., "code": ...}`
- [ ] **SHELL-06**: App works with no `OPENROUTER_API_KEY` (streaming, trading, watchlist all functional)

### Data

- [ ] **DATA-01**: SQLite schema (users_profile, watchlist, positions, trades, portfolio_snapshots, chat_messages) per PLAN.md §7 is created automatically if missing, at `DB_PATH` (default `db/finally.db`)
- [ ] **DATA-02**: Fresh DB is seeded with default user ($10,000 cash) and the 10 default watchlist tickers
- [ ] **DATA-03**: A baseline portfolio snapshot exists after first start and after reset, so the P&L chart always has data
- [ ] **DATA-04**: A background task records a portfolio snapshot every 30 seconds and survives transient errors

### Trading

- [ ] **TRADE-01**: User can buy shares at the current cached price; cash decreases and position is created/updated with weighted-average cost
- [ ] **TRADE-02**: User can sell shares; cash increases, `avg_cost` unchanged, position row deleted when remaining qty < 1e-6
- [ ] **TRADE-03**: Trades are rejected with the correct code: `NO_PRICE`, `INVALID_QUANTITY` (≤0 or rounds to 0 at 4dp), `INSUFFICIENT_CASH`, `INSUFFICIENT_SHARES`, `INVALID_TICKER`
- [ ] **TRADE-04**: Cash rounds to 2dp and quantity to 4dp after every change; money math avoids float drift
- [ ] **TRADE-05**: Each trade (cash, position, trade log, snapshot) is one SQLite transaction under a single process-wide asyncio lock; concurrent trades cannot overdraw cash
- [ ] **TRADE-06**: Buying an unwatched ticker is allowed and keeps it priced while held; the priced set (watchlist ∪ positions) is resynced after every trade, watchlist change, and reset
- [ ] **TRADE-07**: Manual and LLM trades go through the same execution function

### API

- [ ] **API-01**: `GET /api/portfolio` returns cash, positions_value, total_value, unrealized_pnl, and positions (with `current_price` falling back to `avg_cost` when unpriced) in the PLAN.md §8 shape
- [ ] **API-02**: `POST /api/portfolio/trade` returns `{trade, portfolio}` on success
- [ ] **API-03**: `GET /api/portfolio/history` returns `{snapshots: [{total_value, recorded_at}]}`
- [ ] **API-04**: `POST /api/reset` clears positions, trades, snapshots, chat; restores $10k and default watchlist; returns fresh portfolio
- [ ] **API-05**: `GET /api/watchlist` returns tickers with latest price fields (null when unpriced)
- [ ] **API-06**: `POST /api/watchlist` adds a normalized ticker idempotently; Massive mode rejects unknown tickers with `UNKNOWN_TICKER`
- [ ] **API-07**: `DELETE /api/watchlist/{ticker}` returns 204, or 404 `NOT_FOUND` if not watched; a held ticker stays priced
- [ ] **API-08**: `GET /api/chat` returns stored conversation history (role, content, actions, created_at) in chronological order *(addition to PLAN.md — approved by user)*

### Chat (LLM)

- [ ] **CHAT-01**: `POST /api/chat` returns `{message, actions}`; each action carries `status` `ok`/`error` (with `error`, `code`) and failed actions don't stop the rest
- [ ] **CHAT-02**: Prompt includes portfolio context (cash, positions with P&L, watchlist with live prices, total value) and the last 20 messages with their stored actions
- [ ] **CHAT-03**: Real mode calls LiteLLM → OpenRouter asynchronously (never blocks SSE), with the PLAN.md §9 model `nvidia/nemotron-3-ultra-550b-a55b:free`, served by OpenRouter's Nvidia free endpoint (no Cerebras provider pinning or fallback-disabling that would 404); the structured-output schema is requested as PLAN.md §9 specifies
- [ ] **CHAT-04**: Response parsing is tolerant (schema stated in prompt, JSON extracted from fences/prose, Pydantic-validated); on failure the raw text or a generic apology is returned with no actions — never a 500
- [ ] **CHAT-05**: LLM-requested trades and watchlist changes auto-execute in order, through the same services as manual actions
- [ ] **CHAT-06**: User message and assistant message (with actions JSON) are stored in `chat_messages`
- [ ] **CHAT-07**: `LLM_MOCK=true` returns deterministic responses for the five PLAN.md §9 patterns (first match, case-insensitive) and runs them through the normal execution path
- [ ] **CHAT-08**: Without an API key (and mock off), chat returns 200 with the exact "AI chat isn't configured…" message and empty actions
- [ ] **CHAT-09**: A live smoke script verifies the PLAN.md §9 model returns parseable output via the OpenRouter Nvidia free endpoint

### Frontend — Market

- [ ] **UI-01**: Next.js TypeScript static export with Tailwind dark theme (#0d1117 / #1a1a2e, accent #ecad0a, blue #209dd7, purple #753991 submit buttons)
- [ ] **UI-02**: Single `EventSource` to `/api/stream/prices` feeds a per-ticker client price-history store (capped ring buffer)
- [ ] **UI-03**: Header shows live total portfolio value, cash balance, and a connection dot (green OPEN / yellow CONNECTING / red CLOSED)
- [ ] **UI-04**: Watchlist panel shows ticker, price, daily change %, and a sparkline for each watched ticker
- [ ] **UI-05**: Price cell flashes green on uptick / red on downtick, fading ~500ms, re-triggering on each change, no flash on flat
- [ ] **UI-06**: User can add a ticker to and remove a ticker from the watchlist in the UI
- [ ] **UI-07**: Clicking a watchlist ticker shows a larger price-over-time chart for it in the main chart area (a ticker is selected by default)

### Frontend — Portfolio & Trading

- [ ] **UI-08**: Trade bar (ticker, quantity, Buy, Sell) executes market orders; buttons disable in flight; API errors show next to the bar
- [ ] **UI-09**: Positions table shows ticker, quantity, avg cost, current price, unrealized P&L, % change — recomputed live from SSE prices
- [ ] **UI-10**: Portfolio heatmap (Recharts treemap) sizes rectangles by weight and colors by `pnl_percent` (gray at 0, full saturation at ±10%, clamped); each rect has `data-pnl`
- [ ] **UI-11**: P&L line chart plots `portfolio_snapshots` total value over time
- [ ] **UI-12**: Portfolio refetches after trade, after chat with any `ok` action, and after reset; watchlist refetches after add/remove; history refetches after each trade
- [ ] **UI-13**: Every panel has a clear empty/loading state (no NaN, no blank charts); numbers use consistent formatting
- [ ] **UI-14**: Recharts animations are disabled on streaming charts

### Frontend — Chat

- [ ] **UI-15**: Docked, collapsible AI chat panel with message input, scrolling history, and a loading indicator while awaiting a response
- [ ] **UI-16**: Each returned action renders inline as a confirmation (ok) or error (with message)
- [ ] **UI-17**: Chat history is restored from `GET /api/chat` on page load

### Demo Polish (user-approved additions)

- [ ] **POLISH-01**: Header reset button calls `POST /api/reset` and refreshes all panels
- [ ] **POLISH-02**: Suggested prompt chips in chat (e.g. "buy 5 NVDA") that work in mock mode too
- [ ] **POLISH-03**: Action chips reveal in sequence and the affected position/watchlist row is briefly highlighted
- [ ] **POLISH-04**: Charts show hover tooltips; P&L chart shows a $10,000 reference line

### Frontend Tests

- [ ] **FTEST-01**: Unit tests cover live portfolio calculations (market value, P&L, total from portfolio + SSE prices)
- [ ] **FTEST-02**: Unit tests cover heatmap color scale (gray at 0, clamp at ±10%)
- [ ] **FTEST-03**: Unit tests cover price flash class triggering on up/down changes

### Deployment

- [ ] **DEPLOY-01**: Multi-stage Dockerfile (Node 20 → Python 3.12 slim, uv frozen sync) builds the frontend export and serves everything on port 8000 with a single uvicorn worker
- [ ] **DEPLOY-02**: DB persists in named volume `finally-data` at `/app/db` across container restarts
- [ ] **DEPLOY-03**: `scripts/start_windows.ps1` builds if needed (or `--build`), runs container with volume, port, `.env`, prints URL; idempotent
- [ ] **DEPLOY-04**: `scripts/stop_windows.ps1` stops/removes the container, keeps the volume; idempotent
- [ ] **DEPLOY-05**: `scripts/start_mac.sh` / `stop_mac.sh` equivalents exist
- [ ] **DEPLOY-06**: Container stops promptly (open SSE streams don't hang shutdown) and reports healthy via healthcheck

### E2E

- [ ] **E2E-01**: `test/docker-compose.test.yml` runs app (`LLM_MOCK=true`) + pinned Playwright container, gated on app health
- [ ] **E2E-02**: Each test calls `POST /api/reset` first; suite runs with one worker
- [ ] **E2E-03**: Fresh start: default watchlist, $10k balance, prices streaming
- [ ] **E2E-04**: Add and remove a watchlist ticker
- [ ] **E2E-05**: Buy shares: cash decreases, position appears
- [ ] **E2E-06**: Sell shares: cash increases, position updates/disappears
- [ ] **E2E-07**: Heatmap renders with correct colors (`data-pnl` + fill); P&L chart has data points
- [ ] **E2E-08**: Mock chat "buy 1 AAPL" shows response and inline trade action
- [ ] **E2E-09**: SSE resilience: status dot green; after reload it returns green and prices resume
- [ ] **E2E-10**: Full suite passes 3 consecutive cold runs

## v2 Requirements

### Platform

- **PLAT-01**: Bump Docker build stage to Node 22 (Node 20 EOL)
- **PLAT-02**: Cloud deployment (AWS App Runner / Render) with Terraform in `deploy/`

### Chart

- **CHART-01**: Timeframe selection / candlesticks on main chart

## Out of Scope

| Feature | Reason |
|---------|--------|
| Authentication / multi-user | Single `default` user by design; schema is multi-user-ready |
| Limit orders, order book, fees, partial fills | Market orders only — PLAN.md design choice |
| Realized P&L | Intentionally not tracked (PLAN.md §7) |
| Trade confirmation dialogs | Deliberate for fluid demo / agentic showcase |
| Token-by-token LLM streaming | One complete response; loading indicator suffices |
| Price-history API endpoint | History accumulates client-side from SSE |
| Multi-call LLM / tool loops | Exactly one LLM call per message (PLAN.md §9) |
| Switching off the PLAN.md §9 model / `LLM_MODEL` override | User chose the Nvidia free endpoint and to follow PLAN.md; tolerant parsing (CHAT-04) covers missing schema enforcement |
| Recovering earlier lost implementation | User chose build-fresh |
| Light theme, draggable layout, alerts, news | Not in spec; dilutes terminal aesthetic |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 1 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| FOUND-06 | Phase 1 | Pending |
| SHELL-01 | Phase 2 | Pending |
| SHELL-02 | Phase 2 | Pending |
| SHELL-03 | Phase 2 | Pending |
| SHELL-04 | Phase 2 | Pending |
| SHELL-05 | Phase 2 | Pending |
| SHELL-06 | Phase 2 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | Pending |
| DATA-03 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| TRADE-01 | Phase 2 | Pending |
| TRADE-02 | Phase 2 | Pending |
| TRADE-03 | Phase 2 | Pending |
| TRADE-04 | Phase 2 | Pending |
| TRADE-05 | Phase 2 | Pending |
| TRADE-06 | Phase 2 | Pending |
| TRADE-07 | Phase 2 | Pending |
| API-01 | Phase 2 | Pending |
| API-02 | Phase 2 | Pending |
| API-03 | Phase 2 | Pending |
| API-04 | Phase 2 | Pending |
| API-05 | Phase 2 | Pending |
| API-06 | Phase 2 | Pending |
| API-07 | Phase 2 | Pending |
| API-08 | Phase 3 | Pending |
| CHAT-01 | Phase 3 | Pending |
| CHAT-02 | Phase 3 | Pending |
| CHAT-03 | Phase 3 | Pending |
| CHAT-04 | Phase 3 | Pending |
| CHAT-05 | Phase 3 | Pending |
| CHAT-06 | Phase 3 | Pending |
| CHAT-07 | Phase 3 | Pending |
| CHAT-08 | Phase 3 | Pending |
| CHAT-09 | Phase 3 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| UI-05 | Phase 4 | Pending |
| UI-06 | Phase 4 | Pending |
| UI-07 | Phase 4 | Pending |
| UI-08 | Phase 5 | Pending |
| UI-09 | Phase 5 | Pending |
| UI-10 | Phase 5 | Pending |
| UI-11 | Phase 5 | Pending |
| UI-12 | Phase 5 | Pending |
| UI-13 | Phase 5 | Pending |
| UI-14 | Phase 5 | Pending |
| UI-15 | Phase 5 | Pending |
| UI-16 | Phase 5 | Pending |
| UI-17 | Phase 5 | Pending |
| POLISH-01 | Phase 5 | Pending |
| POLISH-02 | Phase 5 | Pending |
| POLISH-03 | Phase 5 | Pending |
| POLISH-04 | Phase 5 | Pending |
| FTEST-01 | Phase 5 | Pending |
| FTEST-02 | Phase 5 | Pending |
| FTEST-03 | Phase 5 | Pending |
| DEPLOY-01 | Phase 6 | Pending |
| DEPLOY-02 | Phase 6 | Pending |
| DEPLOY-03 | Phase 6 | Pending |
| DEPLOY-04 | Phase 6 | Pending |
| DEPLOY-05 | Phase 6 | Pending |
| DEPLOY-06 | Phase 6 | Pending |
| E2E-01 | Phase 7 | Pending |
| E2E-02 | Phase 7 | Pending |
| E2E-03 | Phase 7 | Pending |
| E2E-04 | Phase 7 | Pending |
| E2E-05 | Phase 7 | Pending |
| E2E-06 | Phase 7 | Pending |
| E2E-07 | Phase 7 | Pending |
| E2E-08 | Phase 7 | Pending |
| E2E-09 | Phase 7 | Pending |
| E2E-10 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 80 total
- Mapped to phases: 80
- Unmapped: 0

---
*Requirements defined: 2026-10-13*
*Last updated: 2026-10-13 after LLM provider decision (Nvidia free endpoint, per PLAN.md)*
