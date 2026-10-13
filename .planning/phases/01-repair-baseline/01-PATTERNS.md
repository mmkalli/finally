# Phase 1: Repair & Baseline - Pattern Map

**Mapped:** 2026-10-13
**Files analyzed:** 19 (9 conflict repairs, 3 new tests/CI, 3 hygiene files, 1 dependency edit, 1 cleanup set, 2 already-resolved)
**Analogs found:** 6 / 19 meaningful (conflict repairs are mechanical and need no analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/market/{cache,interface,massive,models,seed_data,simulator,tickers}.py` | source (repair) | n/a | RESEARCH.md inventory (delete lines 1-4 hunk) | mechanical |
| `backend/app/market/__init__.py` | source (repair) | n/a | RESEARCH.md: keep "theirs" hunks 2,3; drop hunk 1 | mechanical |
| `backend/app/market/demo.py` | source (repair) | n/a | RESEARCH.md: keep HEAD in all 3 hunks | mechanical |
| `backend/pyproject.toml` + `backend/uv.lock` | config | batch | existing `backend/pyproject.toml` | exact |
| `backend/tests/test_no_conflict_markers.py` | test | batch (file scan) | `backend/tests/market/test_cache_and_tickers.py` (style) + RESEARCH.md guard sketch | role-match |
| `backend/tests/test_baseline.py` | test | request-response (import/parse) | `backend/tests/market/test_cache_and_tickers.py` | role-match |
| `.github/workflows/ci.yml` | config (CI) | event-driven | `.github/workflows/claude.yml` | role-match |
| `.gitattributes` | config | n/a | none | no analog |
| `.dockerignore` | config | n/a | `.gitignore` (root) | partial |
| `.env.example` | config | n/a | PLAN.md section 5 (verbatim) | exact (spec) |
| stale `__pycache__`-only dirs (delete) | cleanup | n/a | n/a | n/a |

## Pattern Assignments

### `backend/tests/test_no_conflict_markers.py` and `backend/tests/test_baseline.py` (test)

**Analog:** `backend/tests/market/test_cache_and_tickers.py`

Conventions to copy (lines 1-8): first-line path comment, stdlib imports, blank line, `pytest`, then `from app.market import ...` (rootdir on path via `pythonpath = ["."]`). Plain top-level `def test_*()` functions, no classes, short one-behavior tests, `assert` with tuple comparisons. `backend/tests/__init__.py` exists, so `backend/tests/` is a package; new test files go directly in `backend/tests/` (no `__init__` needed).

```python
# backend/tests/market/test_cache_and_tickers.py
from datetime import datetime, timezone

import pytest

from app.market import InvalidTickerError, PriceCache, PriceUpdate, normalize_ticker


def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    u = cache.update("AAPL", 190.123)
    assert (u.price, u.previous_price, u.open_price) == (190.12, 190.12, 190.12)
```

Config (`backend/pyproject.toml`): `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["."]`. The guard test is sync, so no marks are needed. Use the RESEARCH.md guard sketch (lines 85-118) as the body: marker regex built from `"<" * 7` / `">" * 7` fragments so the file never matches itself, `git ls-files --cached --others --exclude-standard` with an `rglob` fallback, `ROOT = Path(__file__).resolve().parents[2]` (tests/ -> backend/ -> repo root). Add the regex self-test (`MARKER.search("<"*7 + " HEAD\nx")` truthy; `MARKER.search("x " + "<"*7 + " y")` falsy). Never write a literal line starting with seven `<` or `>`.

`test_baseline.py`: `importlib.import_module("app.market")` smoke plus `tomllib.loads((ROOT/"backend"/"pyproject.toml").read_text())` asserting dependency names include `litellm`, `pydantic`, `python-dotenv`, `tzdata`. Use `Path(__file__).resolve().parents[1] / "pyproject.toml"` for the pyproject path.

---

### `backend/pyproject.toml` (config)

**Analog:** itself (current resolved state). Dependency lines carry trailing inline comments, dev tools live in `[dependency-groups]`, and `[tool.uv] package = false` must stay (no `[build-system]`).

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",          # Massive client (async). ...
    "tzdata>=2024.1",       # zoneinfo data for America/New_York; Windows has no system tz database
]
[tool.uv]
package = false
```

Run `uv add "litellm>=1.105,<1.106" "pydantic>=2.14,<3" "python-dotenv>=1.2"` from `backend/`; keep the `tzdata` line.

---

### `.github/workflows/ci.yml` (CI, event-driven)

**Analog:** `.github/workflows/claude.yml` (only other workflows: `claude.yml`, `claude-code-review.yml`; neither runs tests)

Copy conventions: `name:` header, top-level `on:`, `runs-on: ubuntu-latest`, explicit least-privilege `permissions:` block, and `actions/checkout@v4` (lines 20-26):

```yaml
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1
```

Differences: trigger `on: [push, pull_request]`; use `defaults.run.working-directory: backend`; install uv via `astral-sh/setup-uv` (tag unverified, planner should look up the current major, or fall back to `pip install uv`); Python 3.12; steps `uv sync --frozen`, a marker grep `! git grep -nE '^(<{7}|>{7})( |$)' -- . ':!backend/uv.lock'` (run from repo root since `git grep -- .` is cwd-relative, use `working-directory: .` for that step), then `uv run pytest`. Do not use secrets.

---

### `.dockerignore` (config)

**Analog (partial):** root `.gitignore`, which already ignores `__pycache__/`, `.env`, `.venv`, `node_modules/`, `.next/`, `frontend/out/`. Plain gitignore-style one-pattern-per-line with `#` section comments. Mirror those entries and add: `.git`, `.github`, `.claude`, `.claude-plugin`, `.planning`, `planning`, `independent-reviewer`, `.env.*` followed by `!.env.example`, `db/*.db`, `test/`. Do not ignore `backend/uv.lock` or `frontend/package-lock.json`. Note `.gitignore` uses `.env` (exact name), so `.env.example` is not ignored; verify with `git check-ignore -v .env.example`.

---

### `.env.example` (config)

**Source:** PLAN.md section 5, copy verbatim (RESEARCH.md lines 149-159): `OPENROUTER_API_KEY=your-openrouter-api-key-here`, `MASSIVE_API_KEY=`, `LLM_MOCK=false`, with the three comment blocks. No `MASSIVE_POLL_INTERVAL`.

---

### `.gitattributes` (config)

No analog in repo. Use the explicit patterns only (no `* text=auto`, to keep the diff small): `*.sh text eol=lf`, `Dockerfile text eol=lf`, `*.yml text eol=lf`, `*.yaml text eol=lf`, optionally `*.ps1 text eol=crlf`.

---

### Conflict repairs (`backend/app/market/*.py`)

No analog needed; follow the per-file table in RESEARCH.md (lines 60-73). Mechanical points:
- Seven one-hunk files: delete the marker block at lines 1-4 (HEAD side empty, `=======` at line 2 or 3, "theirs" is the stray `# backend/app/market/<file>.py` header, closing `>>>>>>> 15bd778...`). Confirm the next line is the real first line (`from __future__ import annotations`, `import re`, or docstring).
- `__init__.py`: keep "theirs" bodies of hunks 2 and 3, drop hunk 1 entirely; keep the `from .tickers import ...` line and closing `]`.
- `demo.py`: keep HEAD in all three hunks.
- Files are CRLF; preserve line endings, do not mass-reformat.
- Verify: `cd backend && uv run python -c "import app.market as m; print(m.stream_router, m.sync_priced_tickers)"`.

## Shared Patterns

### Always `uv run`, never bare `python`
**Apply to:** every verification command and CI step. `python` is not on PATH on this Windows machine. Run from `backend/`.

### Guard-regex self-protection
**Apply to:** `test_no_conflict_markers.py` and the CI grep step. Anchor to line start (`^(<{7}|>{7})( |$)`), do not flag bare `=======`, never put a literal marker at line start in any committed file.

### Test style
**Source:** `backend/tests/market/*.py` (first-line path comment, flat `test_*` functions, imports from `app.market`, `tests.market.fake_massive` style absolute imports within the `tests` package). **Apply to:** both new test files.

### Do not commit until green
Commit as separate atomic commits after `uv run pytest` passes (resolution, lock/deps, guard+CI, hygiene).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `.gitattributes` | config | n/a | None exists; use RESEARCH.md explicit patterns |
| `.github/workflows/ci.yml` test/uv steps | CI | event-driven | Existing workflows only run Claude actions; reuse only checkout/permissions conventions |

## Metadata

**Analog search scope:** `.github/workflows/`, `backend/tests/`, `backend/tests/market/`, root `.gitignore`, `backend/pyproject.toml`
**Files scanned:** about 8 (read: test_cache_and_tickers.py head, test_contract.py head, claude.yml, pyproject.toml, .gitignore)
**Pattern extraction date:** 2026-10-13
