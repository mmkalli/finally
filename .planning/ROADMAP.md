# Roadmap: FinAlly — AI Trading Workstation

## Overview

Brownfield start: only the market-data slice exists and it is broken by merge-conflict markers. The path is repair the baseline (hard gate), build the backend core (DB, trading, REST) on top of the market slice, add the LLM chat layer over the same services, build the frontend in two slices (market/watchlist first, then portfolio/trading/chat/polish), package it in a single Docker container with PowerShell/bash scripts, and finish with the Playwright E2E suite that defines "done". `planning/PLAN.md` is the binding contract throughout.

## Phases

- [ ] **Phase 1: Repair & Baseline** - Resolve merge conflicts, fix deps and lockfile, get market tests green, add guards (hard gate)
- [ ] **Phase 2: Backend Core** - App shell, SQLite, trading engine, portfolio/watchlist/reset REST API with uniform errors
- [ ] **Phase 3: LLM Chat** - Mock-first chat endpoint, tolerant structured-output parsing, auto-executed actions, history
- [ ] **Phase 4: Frontend Market** - Next.js shell, SSE price store, header, watchlist with flash and sparklines, main chart
- [ ] **Phase 5: Frontend Portfolio, Chat & Polish** - Trade bar, positions, heatmap, P&L chart, chat panel, demo polish, unit tests
- [ ] **Phase 6: Packaging** - Multi-stage Dockerfile, named volume, PowerShell and bash start/stop scripts
- [ ] **Phase 7: E2E** - Playwright suite in Docker with LLM_MOCK=true, green on three cold runs

## Phase Details

### Phase 1: Repair & Baseline

**Goal**: The existing market-data code imports, its tests pass, and the repo is protected against regressing to a broken state
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06
**Success Criteria** (what must be TRUE):

  1. `import app.market` succeeds and no `<<<<<<<` / `>>>>>>>` markers remain anywhere in the repo
  2. `uv sync` succeeds from a regenerated `uv.lock` with litellm, pydantic, python-dotenv and tzdata declared
  3. `uv run pytest` passes the full market-data suite
  4. A guard test fails if a conflict marker is reintroduced
  5. `.gitattributes`, `.dockerignore`, `.env.example` exist and stale `api/`, `chat/`, `database/`, `portfolio/` pycache dirs are gone

**Plans**: 4 plans

Plans:
**Wave 1**

- [ ] 01-01-PLAN.md — Resolve merge conflicts in the 9 market modules, commit factory.py, market suite green (wave 1)
- [ ] 01-02-PLAN.md — Delete stale pycache dirs; add .gitattributes, .dockerignore, .env.example (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-03-PLAN.md — Package legitimacy checkpoint, uv add litellm/pydantic/python-dotenv, regenerate uv.lock, baseline test (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-04-PLAN.md — Conflict-marker pytest guard + GitHub Actions CI, phase gate (wave 3)

### Phase 2: Backend Core

**Goal**: A running FastAPI app where the user (via REST) can see streaming prices, trade, manage the watchlist, and reset, with every error in the `{error, code}` shape
**Depends on**: Phase 1
**Requirements**: SHELL-01, SHELL-02, SHELL-03, SHELL-04, SHELL-05, SHELL-06, DATA-01, DATA-02, DATA-03, DATA-04, TRADE-01, TRADE-02, TRADE-03, TRADE-04, TRADE-05, TRADE-06, TRADE-07, API-01, API-02, API-03, API-04, API-05, API-06, API-07
**Success Criteria** (what must be TRUE):

  1. Starting the app on an empty DB creates and seeds it ($10,000 cash, 10 default tickers, a baseline snapshot), `/api/health` returns ok, and `/api/stream/prices` streams ticks with no OPENROUTER_API_KEY set
  2. Buying and selling via `POST /api/portfolio/trade` updates cash, weighted-average cost and positions per spec, and each failure returns the correct code (NO_PRICE, INVALID_QUANTITY, INSUFFICIENT_CASH, INSUFFICIENT_SHARES, INVALID_TICKER)
  3. Two concurrent buys cannot overdraw cash, and a held ticker removed from the watchlist stays priced and sellable
  4. Watchlist add (idempotent), delete (204 / 404 NOT_FOUND) and `POST /api/reset` behave per PLAN.md section 8, and portfolio/history responses match the documented shapes
  5. Validation errors (422) and unknown `/api/*` paths return JSON `{error, code}`, never `index.html`; snapshots are recorded every 30s and after each trade

**Plans**: TBD

### Phase 3: LLM Chat

**Goal**: The user can chat with FinAlly via `POST /api/chat`, and requested trades and watchlist changes execute through the same services as manual ones
**Depends on**: Phase 2
**Requirements**: API-08, CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08, CHAT-09
**Success Criteria** (what must be TRUE):

  1. With `LLM_MOCK=true`, "buy 1 AAPL" / "sell" / "add" / "watch" / "remove" messages return the exact mock text and execute the action; any other message gets the default reply
  2. A chat with a failing action (e.g. selling unheld shares) returns 200 with that action marked `error` while the other actions still run
  3. With no API key and mock off, chat returns 200 with the "AI chat isn't configured" message and no actions; malformed LLM output yields raw text or an apology, never a 500
  4. `GET /api/chat` returns the stored conversation, including each assistant message's actions, in chronological order
  5. A slow chat call does not stall the SSE price stream, and a live smoke script confirms the PLAN.md section 9 model returns parseable output via OpenRouter

**Plans**: TBD
**Research flag**: Needs research — OpenRouter routing and supported params, LiteLLM `openrouter/` prefix, `extra_body` / `drop_params` (model stays PLAN.md section 9; no `LLM_MODEL` override)

### Phase 4: Frontend Market

**Goal**: Opening the app shows a dark terminal with live-streaming prices, flashing watchlist rows with sparklines, and a selectable main chart
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07
**Success Criteria** (what must be TRUE):

  1. The static export loads from the backend at `/` in the specified dark theme and palette
  2. The header shows a connection dot (green / yellow / red per EventSource state), cash balance, and live total portfolio value
  3. Each watchlist row shows ticker, price, daily change % and a sparkline that fills progressively; the price cell flashes green on uptick and red on downtick, fading in about 500ms, with no flash on flat
  4. User can add and remove a watchlist ticker from the UI
  5. Clicking a watchlist ticker shows a larger price-over-time chart for it (one is selected by default)

**Plans**: TBD
**UI hint**: yes
**Research flag**: Needs research — short spike on Recharts 3 behavior and the eslint/vitest/Node version matrix

### Phase 5: Frontend Portfolio, Chat & Polish

**Goal**: The user can trade, watch their portfolio visualized live, and talk to the AI whose actions appear inline, with demo polish applied
**Depends on**: Phase 3, Phase 4
**Requirements**: UI-08, UI-09, UI-10, UI-11, UI-12, UI-13, UI-14, UI-15, UI-16, UI-17, POLISH-01, POLISH-02, POLISH-03, POLISH-04, FTEST-01, FTEST-02, FTEST-03
**Success Criteria** (what must be TRUE):

  1. User can buy and sell from the trade bar (buttons disabled in flight, API errors shown next to the bar), and the positions table, header total, and heatmap update live from SSE prices
  2. The heatmap sizes rectangles by weight and colors by P&L (gray at 0, saturated at +/-10%, `data-pnl` on each rect); the P&L chart plots snapshots with a $10,000 reference line; charts show hover tooltips
  3. User can open the collapsible chat panel, see a loading indicator, and each returned action renders inline as a confirmation or error; prompt chips work in mock mode, action chips reveal in sequence, and the affected row highlights
  4. Reloading the page restores chat history; the header reset button returns everything to the seed state; portfolio, watchlist and history refetch after trades, chat actions and reset
  5. Every panel has a clear empty/loading state (no NaN, no blank charts), and unit tests for live portfolio math, heatmap color scale and flash class pass

**Plans**: TBD
**UI hint**: yes

### Phase 6: Packaging

**Goal**: One PowerShell command builds and launches the whole app in a single container on port 8000 with persistent data
**Depends on**: Phase 5
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, DEPLOY-06
**Success Criteria** (what must be TRUE):

  1. `scripts/start_windows.ps1` builds the image if needed (or with `--build`), runs the container with volume, port and `.env`, prints the URL, and is safe to run twice
  2. `http://localhost:8000` serves the full UI and API from the container with one uvicorn worker
  3. Trades and watchlist changes survive a container stop/start via the `finally-data` volume
  4. `scripts/stop_windows.ps1` stops and removes the container while keeping the volume, and `docker stop` completes promptly despite open SSE streams; the container reports healthy
  5. `start_mac.sh` / `stop_mac.sh` exist with LF line endings and equivalent behavior

**Plans**: TBD

### Phase 7: E2E

**Goal**: The PLAN.md section 12 scenarios pass reliably in Docker, proving the app is done
**Depends on**: Phase 6
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07, E2E-08, E2E-09, E2E-10
**Success Criteria** (what must be TRUE):

  1. `test/docker-compose.test.yml` starts the app (`LLM_MOCK=true`) and a pinned Playwright container gated on app health, running one worker with a reset before each test
  2. Tests pass for fresh start, watchlist add/remove, buy, and sell flows
  3. Tests pass for heatmap colors (`data-pnl` + fill), P&L chart data, mocked chat "buy 1 AAPL" with inline action, and SSE resilience across reload
  4. The full suite passes three consecutive cold runs

**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Repair & Baseline | 0/TBD | Not started | - |
| 2. Backend Core | 0/TBD | Not started | - |
| 3. LLM Chat | 0/TBD | Not started | - |
| 4. Frontend Market | 0/TBD | Not started | - |
| 5. Frontend Portfolio, Chat & Polish | 0/TBD | Not started | - |
| 6. Packaging | 0/TBD | Not started | - |
| 7. E2E | 0/TBD | Not started | - |
