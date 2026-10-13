# FinAlly Project - the Finance Ally

All project documentation is in the `planning` directory.

The key document is PLAN.md included in full here and there are other project documents in planning folder.
For the market data simulator, backend development is completed in backend folder.

@planning/PLAN.md

<!-- GSD:project-start source:PROJECT.md -->
## Project

**FinAlly — AI Trading Workstation**

FinAlly (Finance Ally) is a single-container, Bloomberg-terminal-style trading workstation. It streams live (simulated or Massive/Polygon) market prices, lets the user trade a $10,000 virtual portfolio, and adds an LLM chat copilot that can analyse positions and run trades and watchlist changes itself. It is the capstone demo for an agentic-AI coding course: built entirely by coding agents and judged largely on how it looks and works on first launch.

**Core Value:** One command (`scripts/start_windows.ps1`) launches a container where prices visibly stream, trades execute instantly, and the AI chat can place a trade that shows up inline. If everything else slips, that live loop of streaming, trading and chat must work and look impressive.

### Constraints

- **Spec**: `planning/PLAN.md` is the binding contract — API shapes, error codes, schema, trade rules, mock patterns must match exactly.
- **Tech stack**: FastAPI + uv (Python 3.12), SQLite (stdlib), Next.js TypeScript static export, Tailwind, Recharts, EventSource SSE, LiteLLM — fixed by spec.
- **Deployment**: single Docker container, single port 8000, named volume for DB — fixed by spec.
- **Platform**: must run on Windows via PowerShell scripts + Docker Desktop.
- **Testing**: Playwright runs in its own container (`test/docker-compose.test.yml`), not in the production image.
- **Visual**: dark theme (#0d1117 / #1a1a2e), accent #ecad0a, blue #209dd7, purple #753991 submit buttons.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python >=3.12 (`backend/pyproject.toml` `requires-python`; bytecode is `cpython-312`) - Built: all of `backend/app/market/` and `backend/tests/market/`.
- TypeScript (Next.js frontend) - Planned: `frontend/` does not exist.
- SQL (SQLite schema/seed) - Planned: `backend/app/database/` is an empty directory (pycache only).
## Runtime
- CPython 3.12 (asyncio-based; market sources run as in-process background tasks).
- Planned: Node 20 slim (frontend build stage), Python 3.12 slim (runtime stage) in a multi-stage `Dockerfile` (not present).
- uv (Python). Lockfile: present, `backend/uv.lock` (revision 5).
- `backend/pyproject.toml` has `[tool.uv] package = false` on the HEAD side of the conflict (see Configuration).
- npm for the frontend - Planned.
## Frameworks
- FastAPI >=0.115 (locked 0.143.0) - used for `APIRouter`, `Request`, `StreamingResponse` in `backend/app/market/stream.py` (SSE endpoint `/api/stream/prices`).
- Uvicorn[standard] >=0.30 (locked 0.54.0) - ASGI server.
- httpx >=0.27 (locked 0.28.1) - async client for the Massive REST API in `backend/app/market/massive.py`.
- tzdata >=2024.1 (locked 2026.5) - IANA tz data for `zoneinfo.ZoneInfo("America/New_York")` (Windows has no system tz DB).
- LiteLLM -> OpenRouter (model `nvidia/nemotron-3-ultra-550b-a55b:free`, Cerebras provider) for chat; not in `pyproject.toml` yet.
- Next.js (static export), Tailwind CSS, Recharts - frontend.
- SQLite via stdlib `sqlite3` (a `sqlite3` import appears in the working tree/spec only; no DB code is committed).
- pytest >=8 (locked 9.1.1) and pytest-asyncio >=0.24 (locked 1.4.0), dev dependency group. `asyncio_mode = "auto"`, function-scoped loops.
- Planned: Playwright E2E in `test/`, React Testing Library in `frontend/`.
- hatchling build backend (only on the incoming side of the merge conflict).
- Planned: Docker multi-stage build, `scripts/start_*.sh|ps1`.
## Key Dependencies
- `fastapi`, `uvicorn[standard]` - API + SSE serving.
- `httpx` - Massive client.
- Standard library heavily used: `asyncio`, `dataclasses`, `random`, `math`, `statistics`, `collections.deque/defaultdict`, `zoneinfo`, `logging`, `abc`.
- `tzdata` - required on Windows for market-hours logic.
## Configuration
- `MASSIVE_API_KEY` - empty/absent selects the simulator, set selects Massive (`backend/app/market/factory.py`).
- `MASSIVE_POLL_INTERVAL` - seconds, default 15, floored at 2.0 (`MIN_POLL_INTERVAL`) in `backend/app/market/factory.py`.
- Planned (spec only): `OPENROUTER_API_KEY`, `LLM_MOCK`. `.env.example` is not committed yet; `.env` is gitignored. Never read `.env` contents.
- `backend/pyproject.toml` - **contains unresolved git merge-conflict markers** (`<<<<<<< HEAD` / `=======` / `>>>>>>> 15bd778`) in `dependencies`, `[tool.pytest.ini_options]`, and build sections. HEAD side adds `tzdata` and `[tool.uv] package = false`; the other side adds `testpaths`, `pythonpath`, and hatchling. The file is invalid TOML until resolved.
- `backend/app/market/factory.py` also contains conflict markers at the top of the file.
- `backend/uv.lock` already reflects the HEAD side (includes `tzdata`).
## Platform Requirements
- Python 3.12+, uv. Windows supported (tzdata dependency). Run tests from `backend/` with `uv run pytest`.
- Demo: `backend/app/market/demo.py`.
- Planned: single Docker container on port 8000 with named volume `finally-data` mounted at `/app/db`; optional AWS App Runner/Render. No `Dockerfile`, `docker-compose.yml`, or `scripts/` exist yet.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py`, one concern per module: `backend/app/market/cache.py`, `seed_data.py`, `massive.py`.
- Test files: `test_<topic>.py` in `backend/tests/market/`; non-test helpers there use plain names (`fake_massive.py`).
- `snake_case`. Private helpers prefixed `_` (`_positive` in `backend/app/market/massive.py`). Pure helpers that tests call directly are public (`pick_price`, `latest_published_day`, `normalize_ticker`).
- `snake_case` locals; module constants `UPPER_SNAKE` (`BASE_URL`, `TICKER_RE`, `TRADING_SECONDS_PER_YEAR`, `EMPTY_PRICE_FIELDS`).
- Private instance attrs use a leading underscore (`self._cache`, `self._prices`) exposed via `@property`.
- `PascalCase`. Exceptions end in `Error` (`MarketDataError`, `InvalidTickerError`, `UnknownTickerError`). ABCs are named by role (`MarketDataSource`); implementations `<Impl>DataSource` (`MassiveDataSource`, `SimulatorDataSource`). Type aliases via `Literal` (`Direction`, `Mode`).
## Code Style
- No tool configured. Observed: 4-space indent, double quotes, line length up to ~120 chars, trailing commas in multi-line literals, aligned inline comments, section dividers like `# ---- writes (data source only) ----`.
- Every module starts with `from __future__ import annotations`; use modern typing (`X | None`, `dict[str, float]`, `collections.abc.Iterable`).
- Use `@dataclass(frozen=True, slots=True)` for value objects (`PriceUpdate` in `backend/app/market/models.py`), `@dataclass(slots=True)` for mutable state.
- Keyword-only args (`*,`) for tuning/optional parameters (`PriceCache.update`, `GBMSimulator.__init__`).
- None configured. Dependencies: `backend/pyproject.toml` (requires Python >=3.12).
## Import Organization
## Error Handling
- Domain errors subclass `MarketDataError(ValueError)` in `backend/app/market/tickers.py`, carrying class attrs `code` (matches PLAN.md API error codes e.g. `INVALID_TICKER`) and `http_status`. Routes should translate them to `{"error": msg, "code": code}`.
- Validate input at the boundary with `normalize_ticker()` (trim, uppercase, `^[A-Z.]{1,6}$`); all source methods assume already-normalized tickers.
- Best-effort background work logs and continues rather than raising (`MarketDataSource.sync` catches `UnknownTickerError` and logs a warning).
## Logging
## Comments
- Docstrings on public classes/methods explain contract and invariants (lifecycle, idempotence, what raises), short and prose-style, not Sphinx/Google param lists.
- Inline comments explain why (e.g. rounding only in cache, ET reset window behaviour). Reference spec sections like `(PLAN.md §6)`.
- Tests tag contract cases with comments (`# C1`, `# C2`) mapped to the design doc.
- Many files begin with a path comment `# backend/app/market/<file>.py`.
## Function Design
- Small functions; pure/sync logic separated from async I/O (`GBMSimulator` is pure and deterministic with an injected `random.Random`; `SimulatorDataSource` wraps it in a task).
- Inject dependencies for testability: `client=` (httpx.AsyncClient), `now=` (clock callable), `rng=`, `tick_seconds=`/`poll_interval=`.
- Methods intended to be safely repeatable are idempotent (`add_ticker`, `remove_ticker`, `stop`).
- Return `None` for "no data" (`get`, `get_price`, `pick_price`) rather than raising.
## Module Design
- Single in-memory source of truth: `PriceCache` (no locks; event-loop only, no awaits inside methods).
- Abstract interface `MarketDataSource` in `backend/app/market/interface.py`; new sources must implement `start/stop/add_ticker/remove_ticker/tickers` and call `cache.update`.
- Barrel file: `backend/app/market/__init__.py` (keep `__all__` sorted and updated).
## Known Repository Hazard
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Implementation Status
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
- Single writer (active `MarketDataSource`), many readers (SSE clients, future trade/portfolio code).
- Everything runs on one asyncio event loop; `PriceCache` methods never await so no lock is needed.
- Pure logic (`GBMSimulator`, `pick_price`, `latest_published_day`) separated from async I/O wrappers for testability.
- Time and HTTP are injectable (`MassiveDataSource(client=, now=)`, `GBMSimulator(rng=)`).
- Background tasks must never die: tick bodies wrapped in `try/except Exception` with `log.exception`.
## Layers
- Location: `backend/app/market/models.py`, `tickers.py`, `seed_data.py`
- Depends on: stdlib only
- Used by: all other market modules
- Location: `backend/app/market/cache.py`
- Depends on: `models.py`
- Location: `backend/app/market/interface.py`, `simulator.py`, `massive.py`, `factory.py`
- Depends on: cache, tickers, seed_data, httpx (Massive)
- Location: `backend/app/market/stream.py` (FastAPI router)
- Depends on: cache; expects `request.app.state.price_cache`
- Location: `backend/app/market/priced.py` (sqlite3 connection + source)
## Data Flow
### Price streaming path
### Priced-set sync (planned wiring)
## Key Abstractions
## Entry Points
## Architectural Constraints
- **Threading:** single-threaded asyncio event loop; no worker threads.
- **Global state:** none at module level; cache lives on `app.state.price_cache` (expected, set by future lifespan).
- **Circular imports:** none; `priced.py` imports `interface.py`, not vice versa.
- **Massive free tier:** limited to 5 calls/min, enforced by rolling-window throttle in `massive.py` (`FREE_TIER_CALLS_PER_MINUTE`).
- **Merge conflict markers:** many files in `backend/app/market/` and `backend/pyproject.toml` contain unresolved `<<<<<<< HEAD` / `>>>>>>> 15bd778` markers; they are not importable as-is until resolved. HEAD side includes `tzdata`, `[tool.uv] package = false`; other side includes `priced.py`/`stream_router` exports, hatchling build config, pytest `testpaths`/`pythonpath`.
## Anti-Patterns
### Committing unresolved merge conflicts
### Writing the cache from outside the active source
## Error Handling
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| cerebras-inference | Use this to write code to call an LLM using LiteLLM and OpenRouter with the Cerebras inference provider | `.claude/skills/cerebras/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
