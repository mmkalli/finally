# Codebase Structure

**Analysis Date:** 2026-10-13

## Directory Layout

Existing (excluding `.claude/` tooling):

```
finally/
├── backend/                     # uv Python project (finally-backend)
│   ├── pyproject.toml           # deps: fastapi, uvicorn, httpx, tzdata; dev: pytest, pytest-asyncio (has merge conflict markers)
│   ├── uv.lock
│   ├── app/
│   │   ├── __init__.py
│   │   └── market/              # market data subsystem (only implemented module)
│   │       ├── __init__.py      # public API re-exports
│   │       ├── models.py        # PriceUpdate
│   │       ├── cache.py         # PriceCache
│   │       ├── interface.py     # MarketDataSource ABC
│   │       ├── simulator.py     # GBMSimulator, SimulatorDataSource
│   │       ├── massive.py       # MassiveDataSource
│   │       ├── factory.py       # create_market_data_source
│   │       ├── seed_data.py     # seed prices, profiles, DEFAULT_TICKERS
│   │       ├── tickers.py       # normalize_ticker, errors
│   │       ├── priced.py        # watchlist ∪ positions sync
│   │       ├── stream.py        # SSE router
│   │       └── demo.py          # terminal demo
│   └── tests/market/            # pytest suite (+ fake_massive.py helper)
├── planning/                    # PLAN.md plus MARKET_*.md and MASSIVE_API.md design docs
├── independent-reviewer/        # Claude plugin (hooks) unrelated to app runtime
├── .claude-plugin/              # plugin marketplace manifest
├── .github/workflows/           # claude.yml, claude-code-review.yml
├── CLAUDE.md, README.md, LICENSE, .gitignore
└── .planning/codebase/          # these generated docs
```

PLANNED (in PLAN.md, absent): `frontend/`, `backend/app/database/`, `backend/app/main.py`, `scripts/`, `test/`, `db/`, `Dockerfile`, `docker-compose.yml`, `.env.example`.

## Directory Purposes

**`backend/app/market/`:**
- Purpose: everything about producing, caching and streaming prices
- Key files: `interface.py`, `cache.py`, `simulator.py`, `massive.py`, `stream.py`

**`backend/tests/market/`:**
- Purpose: tests per module: `test_cache_and_tickers.py`, `test_contract.py` (both sources vs ABC), `test_massive.py` (uses `fake_massive.py` + `httpx.MockTransport`), `test_simulator.py`, `test_stream.py`

**`planning/`:**
- Purpose: shared agent contract; `MARKET_DATA_DESIGN.md`, `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md` describe the market subsystem

## Key File Locations

**Entry Points:**
- `backend/app/market/stream.py`: SSE route (`stream_router`)
- `backend/app/market/demo.py`: CLI demo (`uv run python -m app.market.demo`)

**Configuration:**
- `backend/pyproject.toml`: deps, pytest (`asyncio_mode = "auto"`)
- Env vars read in `backend/app/market/factory.py`: `MASSIVE_API_KEY`, `MASSIVE_POLL_INTERVAL`

**Core Logic:**
- `backend/app/market/simulator.py`, `backend/app/market/massive.py`

**Testing:**
- `backend/tests/market/`

## Naming Conventions

**Files:** lowercase snake_case modules, one concern each (`seed_data.py`, `fake_massive.py`); tests `test_<topic>.py`.
**Directories:** lowercase, package per domain (`market/`); future `database/`.
**Code:** classes PascalCase (`PriceCache`, `SimulatorDataSource`); functions snake_case; private members `_leading_underscore`; constants UPPER_SNAKE (`TICK_SECONDS`). Modules start with `from __future__ import annotations` and use `log = logging.getLogger(__name__)`. Source files use `dataclass(frozen=True, slots=True)` for value types.

## Where to Add New Code

**New market source:** subclass `MarketDataSource` in `backend/app/market/<name>.py`, register in `factory.py`, export in `__init__.py`, add to the contract tests in `backend/tests/market/test_contract.py`.
**New backend domain (portfolio, chat, database):** new package under `backend/app/` (e.g. `backend/app/database/`, `backend/app/portfolio/`, `backend/app/llm/`) with an `APIRouter`; wire into a new `backend/app/main.py` lifespan, mount static files last.
**Tests:** `backend/tests/<package>/test_<module>.py` mirroring `app/`.
**Utilities:** keep within the owning package; no shared utils module exists.
**Frontend:** `frontend/` (Next.js, `output: 'export'`), per PLAN.md section 10.

## Special Directories

**`backend/.venv`, `__pycache__/`:** generated, gitignored.
**`.planning/codebase/`:** generated analysis docs.
**`.claude/`:** GSD/agent tooling, ignored for architecture purposes.

---

*Structure analysis: 2026-10-13*
