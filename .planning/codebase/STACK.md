# Technology Stack

**Analysis Date:** 2026-10-13

Status legend: **Built** = exists in the repo. **Planned** = described in `planning/PLAN.md` only; no code yet.

## Languages

**Primary:**
- Python >=3.12 (`backend/pyproject.toml` `requires-python`; bytecode is `cpython-312`) - Built: all of `backend/app/market/` and `backend/tests/market/`.

**Secondary:**
- TypeScript (Next.js frontend) - Planned: `frontend/` does not exist.
- SQL (SQLite schema/seed) - Planned: `backend/app/database/` is an empty directory (pycache only).

## Runtime

**Environment:**
- CPython 3.12 (asyncio-based; market sources run as in-process background tasks).
- Planned: Node 20 slim (frontend build stage), Python 3.12 slim (runtime stage) in a multi-stage `Dockerfile` (not present).

**Package Manager:**
- uv (Python). Lockfile: present, `backend/uv.lock` (revision 5).
- `backend/pyproject.toml` has `[tool.uv] package = false` on the HEAD side of the conflict (see Configuration).
- npm for the frontend - Planned.

## Frameworks

**Core (Built):**
- FastAPI >=0.115 (locked 0.143.0) - used for `APIRouter`, `Request`, `StreamingResponse` in `backend/app/market/stream.py` (SSE endpoint `/api/stream/prices`).
- Uvicorn[standard] >=0.30 (locked 0.54.0) - ASGI server.
- httpx >=0.27 (locked 0.28.1) - async client for the Massive REST API in `backend/app/market/massive.py`.
- tzdata >=2024.1 (locked 2026.5) - IANA tz data for `zoneinfo.ZoneInfo("America/New_York")` (Windows has no system tz DB).

**Core (Planned):**
- LiteLLM -> OpenRouter (model `nvidia/nemotron-3-ultra-550b-a55b:free`, Cerebras provider) for chat; not in `pyproject.toml` yet.
- Next.js (static export), Tailwind CSS, Recharts - frontend.
- SQLite via stdlib `sqlite3` (a `sqlite3` import appears in the working tree/spec only; no DB code is committed).

**Testing:**
- pytest >=8 (locked 9.1.1) and pytest-asyncio >=0.24 (locked 1.4.0), dev dependency group. `asyncio_mode = "auto"`, function-scoped loops.
- Planned: Playwright E2E in `test/`, React Testing Library in `frontend/`.

**Build/Dev:**
- hatchling build backend (only on the incoming side of the merge conflict).
- Planned: Docker multi-stage build, `scripts/start_*.sh|ps1`.

## Key Dependencies

**Critical:**
- `fastapi`, `uvicorn[standard]` - API + SSE serving.
- `httpx` - Massive client.
- Standard library heavily used: `asyncio`, `dataclasses`, `random`, `math`, `statistics`, `collections.deque/defaultdict`, `zoneinfo`, `logging`, `abc`.

**Infrastructure:**
- `tzdata` - required on Windows for market-hours logic.

## Configuration

**Environment (read in code):**
- `MASSIVE_API_KEY` - empty/absent selects the simulator, set selects Massive (`backend/app/market/factory.py`).
- `MASSIVE_POLL_INTERVAL` - seconds, default 15, floored at 2.0 (`MIN_POLL_INTERVAL`) in `backend/app/market/factory.py`.
- Planned (spec only): `OPENROUTER_API_KEY`, `LLM_MOCK`. `.env.example` is not committed yet; `.env` is gitignored. Never read `.env` contents.

**Build:**
- `backend/pyproject.toml` - **contains unresolved git merge-conflict markers** (`<<<<<<< HEAD` / `=======` / `>>>>>>> 15bd778`) in `dependencies`, `[tool.pytest.ini_options]`, and build sections. HEAD side adds `tzdata` and `[tool.uv] package = false`; the other side adds `testpaths`, `pythonpath`, and hatchling. The file is invalid TOML until resolved.
- `backend/app/market/factory.py` also contains conflict markers at the top of the file.
- `backend/uv.lock` already reflects the HEAD side (includes `tzdata`).

## Platform Requirements

**Development:**
- Python 3.12+, uv. Windows supported (tzdata dependency). Run tests from `backend/` with `uv run pytest`.
- Demo: `backend/app/market/demo.py`.

**Production:**
- Planned: single Docker container on port 8000 with named volume `finally-data` mounted at `/app/db`; optional AWS App Runner/Render. No `Dockerfile`, `docker-compose.yml`, or `scripts/` exist yet.

---

*Stack analysis: 2026-10-13*
