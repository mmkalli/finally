# FinAlly — AI Trading Workstation

## What This Is

FinAlly (Finance Ally) is a single-container, Bloomberg-terminal-style trading workstation. It streams live (simulated or Massive/Polygon) market prices, lets the user trade a $10,000 virtual portfolio, and adds an LLM chat copilot that can analyse positions and run trades and watchlist changes itself. It is the capstone demo for an agentic-AI coding course: built entirely by coding agents and judged largely on how it looks and works on first launch.

## Core Value

One command (`scripts/start_windows.ps1`) launches a container where prices visibly stream, trades execute instantly, and the AI chat can place a trade that shows up inline. If everything else slips, that live loop of streaming, trading and chat must work and look impressive.

## Requirements

### Validated

<!-- Inferred from existing code (backend/app/market/), pending merge-conflict repair -->

- ✓ Market data abstraction: `MarketDataSource` ABC with GBM simulator (correlated moves, jump events, seed prices, random profile for unknown tickers) and Massive REST poller, selected by `MASSIVE_API_KEY` — existing
- ✓ In-memory `PriceCache` with price / previous_price / open_price / timestamp and a version counter — existing
- ✓ SSE endpoint `GET /api/stream/prices` (full snapshot on connect, deltas after) — existing
- ✓ Ticker normalisation and validation (`^[A-Z.]{1,6}$`, `INVALID_TICKER` / `UNKNOWN_TICKER` error hierarchy) — existing
- ✓ Priced-ticker set = watchlist ∪ open positions (`priced.py`; depends on DB tables not yet built) — existing
- ✓ Market data unit tests (contract suite across sources, simulator, Massive fakes) — existing

Note: these capabilities exist in source but are currently **broken**: commit `b3dc60e` left merge-conflict markers in 9 `backend/app/market/` modules. They count as validated only once repaired and tests pass.

### Active

- [ ] Repair merge-conflict markers in market modules; regenerate lockfile; market test suite green
- [ ] Delete stale `__pycache__` dirs for `api/`, `chat/`, `database/`, `portfolio/` (build fresh, no recovery)
- [ ] FastAPI app entry with lifespan: DB init + seed, market data task, 30s snapshot task; static mount after `/api` routes
- [ ] SQLite schema (users_profile, watchlist, positions, trades, portfolio_snapshots, chat_messages) with `user_id="default"`, seeded on first start
- [ ] Trade execution per PLAN.md §7 rules (NO_PRICE, INVALID_QUANTITY, INSUFFICIENT_CASH/SHARES, rounding, weighted avg cost, single asyncio.Lock + transaction, post-trade snapshot)
- [ ] REST API per PLAN.md §8: portfolio, trade, history, reset, watchlist CRUD, chat, health — uniform `{error, code}` error shape
- [ ] LLM chat via LiteLLM → OpenRouter (Cerebras, structured outputs), 20-message history with stored actions, auto-execution of trades/watchlist changes, `LLM_MOCK` deterministic mode, graceful no-key message
- [ ] Next.js static-export frontend: watchlist with flashing prices + sparklines, main chart, treemap heatmap (`data-pnl`), P&L chart, positions table, trade bar, AI chat panel, header with live total + connection dot
- [ ] Multi-stage Dockerfile (Node 20 → Python 3.12), named volume `finally-data:/app/db`, `.env.example`
- [ ] Start/stop scripts (PowerShell required; bash variants per spec), idempotent
- [ ] Backend pytest coverage for portfolio, LLM, API routes; frontend unit tests for pure calc logic
- [ ] Playwright E2E suite in `test/` with `docker-compose.test.yml`, `LLM_MOCK=true`, reset per test — all PLAN.md §12 scenarios green

### Out of Scope

- Deviations from `planning/PLAN.md` — PLAN.md is the contract; research informs *how*, not *what*
- Recovering lost earlier implementation from history — user chose to build fresh
- Authentication / multi-user — single hardcoded `default` user by design (schema is multi-user-ready)
- Limit orders, order book, partial fills, fees — market orders only by design
- Realized P&L tracking — intentionally not stored or displayed
- Token-by-token LLM streaming — Cerebras is fast enough; loading indicator suffices
- Price-history API endpoint — sparklines/charts accumulate client-side from SSE
- Cloud deployment / Terraform — stretch goal, not core
- Confirmation dialogs for trades (manual or AI) — deliberate for fluid demo

## Context

- **Brownfield:** only the market-data slice exists (`backend/app/market/`, `backend/tests/market/`). Codebase map in `.planning/codebase/` (ARCHITECTURE, STACK, CONCERNS, CONVENTIONS, INTEGRATIONS, STRUCTURE, TESTING).
- **Broken state:** merge-conflict markers make `import app.market` fail. `pyproject.toml` and `factory.py` are already resolved (uncommitted). CONCERNS.md has per-file resolution guidance (keep "theirs" in `__init__.py`, HEAD in `demo.py`, keep `tzdata`, `[tool.uv] package = false`).
- **Agent docs:** `planning/` holds PLAN.md (master spec) plus MARKET_DATA_DESIGN, MARKET_INTERFACE, MARKET_SIMULATOR, MASSIVE_API.
- **LLM:** use the `cerebras-inference` skill (`.claude/skills/cerebras/`): LiteLLM → OpenRouter, model `nvidia/nemotron-3-ultra-550b-a55b:free`, Cerebras provider, structured outputs. `OPENROUTER_API_KEY` is in root `.env`.
- **Audience:** course capstone demo — first-launch polish and the "wow" of AI executing trades matter most.
- **Dev environment:** Windows 11; PowerShell start/stop scripts must work.

## Constraints

- **Spec**: `planning/PLAN.md` is the binding contract — API shapes, error codes, schema, trade rules, mock patterns must match exactly.
- **Tech stack**: FastAPI + uv (Python 3.12), SQLite (stdlib), Next.js TypeScript static export, Tailwind, Recharts, EventSource SSE, LiteLLM — fixed by spec.
- **Deployment**: single Docker container, single port 8000, named volume for DB — fixed by spec.
- **Platform**: must run on Windows via PowerShell scripts + Docker Desktop.
- **Testing**: Playwright runs in its own container (`test/docker-compose.test.yml`), not in the production image.
- **Visual**: dark theme (#0d1117 / #1a1a2e), accent #ecad0a, blue #209dd7, purple #753991 submit buttons.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Milestone 1 = full PLAN.md | User wants the complete app runnable from one command | — Pending |
| Build fresh, delete stale pycache | Lost earlier code not worth recovering | — Pending |
| Done = E2E green in Docker with LLM_MOCK | Objective, reproducible bar for completion | — Pending |
| PLAN.md is locked | Shared contract across agents; avoid drift | — Pending |
| Fix merge conflicts first | Everything downstream depends on importable market code | — Pending |
| LLM: keep PLAN.md §9 model on OpenRouter's Nvidia free endpoint | Cerebras doesn't serve it (checked live 2026-10-13); follow PLAN.md rather than switch models; tolerant JSON parsing covers missing schema enforcement | — Pending |
| Add GET /api/chat + 4 demo-polish items | User-approved additions: chat restore on reload, reset button, prompt chips, action reveal, tooltips/$10k line | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-13 after initialization*
