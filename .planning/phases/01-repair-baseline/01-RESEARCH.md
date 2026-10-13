# Phase 1: Repair & Baseline - Research

**Researched:** 2026-10-13
**Domain:** Git merge-conflict repair, uv/Python dependency baseline, repo hygiene and guard tests
**Confidence:** HIGH (all conflict hunks inspected directly in the working tree)

## Summary

Nine files in `backend/app/market/` still contain conflict markers: `__init__.py`, `cache.py`, `demo.py`, `interface.py`, `massive.py`, `models.py`, `seed_data.py`, `simulator.py`, `tickers.py`. A repo-wide scan (tracked and untracked, excluding `.git`, `node_modules`, `.venv`) found markers in no other files. `pyproject.toml` and `factory.py` are already resolved but uncommitted. `[VERIFIED: grep/git grep in this session]`

Seven of the nine are trivial: the only hunk is a stray `# backend/app/market/<file>.py` header on the "theirs" side versus an empty HEAD side. The fix is to delete the whole hunk. `__init__.py` has three hunks and keeps "theirs" (it exports `priced` and `stream`). `demo.py` has three hunks and keeps HEAD. `stream.py` and `priced.py` have no markers and match the "theirs" API: `priced.py` defines `load_priced_tickers` and `sync_priced_tickers`, and `stream.py` defines `stream_router`. `[VERIFIED: file reads]`

`uv.lock` is a "virtual project" lock (`package = false`) that already contains fastapi, pydantic, python-dotenv and tzdata, but not litellm (0 matches for `name = "litellm"`). `uv add` for litellm, pydantic and python-dotenv regenerates the lock. `uv` 0.13.0 is installed. `[VERIFIED: grep, uv --version]` The working-tree files use CRLF, so the guard regex must tolerate `\r`, and `.gitattributes` should normalize line endings.

**Primary recommendation:** Resolve the nine files per the table below, run `uv add` for the missing deps, run `uv run pytest`, add a repo-scanning pytest guard plus a small GitHub Actions CI workflow, delete stale pycache dirs, and add `.gitattributes`, `.dockerignore`, `.env.example`. Do not commit anything until the tests are green.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Conflict resolution | Backend source | — | Python modules only |
| Dependency baseline | Backend packaging (uv) | — | `pyproject.toml` and `uv.lock` |
| Conflict-marker guard | Test suite (pytest) | CI (GitHub Actions) | Pytest runs locally and in CI; CI makes it unskippable |
| Repo hygiene files | Repo root | Docker build context | `.gitattributes`, `.dockerignore`, `.env.example` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| uv | 0.13.0 (installed) | Env, lock, run | Mandated by PLAN.md §3 |
| pytest + pytest-asyncio | >=8 / >=0.24 (already in dev group) | Test runner | Existing config (`asyncio_mode = "auto"`) |
| litellm | `>=1.105,<1.106` | LLM calls (later phases) | Mandated by PLAN.md §9; version from `.planning/research/STACK.md` (PyPI queried 2026-10-13) `[CITED: .planning/research/STACK.md]` |
| pydantic | `>=2.14,<3` | Models | Same source `[CITED: .planning/research/STACK.md]` |
| python-dotenv | `>=1.2` | `.env` loading | Same source `[CITED: .planning/research/STACK.md]` |
| tzdata | `>=2024.1` (already declared) | `ZoneInfo("America/New_York")` on Windows | `massive.py` needs it |

### Package Legitimacy Audit

slopcheck was not run. All four are long-established packages and were named in the project's own prior research (`STACK.md`, verified there against the PyPI JSON API), but per the provenance rule they are tagged `[ASSUMED]` here. The planner should either run `uv add` as an explicit step with the lock diff reviewed, or add a `checkpoint:human-verify`.

| Package | Registry | Source | slopcheck | Disposition |
|---------|----------|--------|-----------|-------------|
| litellm | PyPI | github.com/BerriAI/litellm | not run | `[ASSUMED]` mandated by PLAN.md; review lock diff |
| pydantic | PyPI | github.com/pydantic/pydantic | not run | `[ASSUMED]` already in lock |
| python-dotenv | PyPI | github.com/theskumar/python-dotenv | not run | `[ASSUMED]` already in lock |
| tzdata | PyPI | github.com/python/tzdata | not run | `[ASSUMED]` already declared and in lock |

**Installation (run from `backend/`):**
```bash
uv add "litellm>=1.105,<1.106" "pydantic>=2.14,<3" "python-dotenv>=1.2"
uv sync
```
`uv add` edits `pyproject.toml` and regenerates `uv.lock` in one step. `uv add --dry-run` is not a valid flag in uv 0.13.0 (checked), so there is no dry run; review `git diff backend/uv.lock --stat` after. If `uv add` re-wraps the dependency comments in `pyproject.toml`, that is harmless. Keep the `tzdata` line.

## Per-File Conflict Resolution Inventory

Every hunk is `<<<<<<< HEAD` ... `=======` ... `>>>>>>> 15bd778770aae61628b6b76861fd1f59cb38fd06`. `[VERIFIED: file reads]`

| File | Hunks | HEAD side | "Theirs" side | Resolution |
|------|-------|-----------|---------------|------------|
| `__init__.py` | 3 | (1) stale comment "priced.py and stream.py ... join this API once the database and routes exist". (2) `from .simulator import GBMSimulator, SimulatorDataSource` only. (3) `__all__` tail `"create_market_data_source", "normalize_ticker",` | (1) `# backend/app/market/__init__.py`. (2) adds `from .priced import load_priced_tickers, sync_priced_tickers`, the simulator import, and `from .stream import stream_router`. (3) `__all__` tail adds `load_priced_tickers`, `stream_router`, `sync_priced_tickers` | Keep "theirs" for hunks 2 and 3. For hunk 1 drop both sides (no comment; the HEAD comment is stale and the other is a stray header). Result must keep the `from .tickers import ...` line and the closing `]` that sit between/after the hunks. |
| `cache.py` | 1 | empty | `# backend/app/market/cache.py` | Delete the whole hunk |
| `interface.py` | 1 | empty | stray header | Delete the whole hunk |
| `massive.py` | 1 | empty | stray header | Delete the whole hunk |
| `models.py` | 1 | empty | stray header | Delete the whole hunk |
| `seed_data.py` | 1 | empty | stray header | Delete the whole hunk |
| `simulator.py` | 1 | empty | stray header | Delete the whole hunk |
| `tickers.py` | 1 | empty | stray header | Delete the whole hunk |
| `demo.py` | 3 | (1) module docstring with `[seconds]`, imports `os`, `sys`, `defaultdict`, `deque`. (2) sparkline renderer, `render()`, and `main(seconds: float \| None = None)` loop with ANSI redraw. (3) `try: asyncio.run(main(float(sys.argv[1]) ...)) except KeyboardInterrupt: pass` | (1) shorter docstring, no extra imports. (2) simple print loop `main(seconds: float = 10.0)`. (3) `asyncio.run(main())` | Keep HEAD in all three hunks (matches CONCERNS.md). The shared lines between hunks (`from . import PriceCache, create_market_data_source`, `from .seed_data import DEFAULT_TICKERS`, `finally: await source.stop()`, `if __name__ == "__main__":`) stay once. |
| `factory.py` | 0 (resolved, uncommitted) | — | — | Already clean; just commit |
| `pyproject.toml` | 0 (resolved, uncommitted) | — | — | Already clean: `tzdata` kept, `testpaths`/`pythonpath` kept, `[tool.uv] package = false`, hatchling dropped. Do NOT reintroduce `[build-system]`: it would contradict the virtual-project lock |
| `stream.py`, `priced.py` | none | — | — | No change. Their leading `# backend/app/market/<file>.py` comment is the same stray-header pattern; removing it is optional cosmetics |

Suggested mechanical approach: for the seven one-hunk files, delete lines 1-4 (verified: markers at lines 1-4 in each, with the `=======` line at 2 or 3). Hand-edit `__init__.py` and `demo.py` with the Edit/Write tool. Afterwards run the conflict scan before pytest.

Check each file starts with the expected next line afterwards (`from __future__ import annotations`, `import re`, or `"""` docstring) so no blank line or BOM issue is introduced. The files are CRLF (`file` reports "with CRLF line terminators"); preserve existing line endings when editing, or accept normalization via `.gitattributes`.

## Architecture Patterns

### Guard test design (FOUND-04)

Place the pytest guard at `backend/tests/test_no_conflict_markers.py`. It walks the repo root (`Path(__file__).resolve().parents[2]`), skips `.git`, `.venv`, `node_modules`, `__pycache__`, `.next`, `out`, `.pytest_cache`, and reads text files tolerantly. It must not match itself, so build the marker regex from fragments or anchor it the way git does. Also scan for the `>>>>>>> ` form. Do not flag a bare `=======` (valid in RST/Markdown headings and used in tests).

```python
# backend/tests/test_no_conflict_markers.py
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built from fragments so this file never matches itself.
MARKER = re.compile(r"^(?:" + "<" * 7 + r"(?: |$)|" + ">" * 7 + r"(?: |$))", re.MULTILINE)
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "out", ".pytest_cache"}
TEXT_SUFFIXES_SKIP = {".png", ".jpg", ".ico", ".pyc", ".db", ".lock"}


def _candidate_files():
    try:  # tracked + untracked-but-not-ignored, honours .gitignore
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        return [ROOT / p for p in out]
    except (OSError, subprocess.CalledProcessError):  # no git (e.g. Docker context)
        return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.parts)]


def test_no_conflict_markers():
    bad = []
    for p in _candidate_files():
        if p.suffix in TEXT_SUFFIXES_SKIP or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if MARKER.search(text):
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, f"unresolved merge-conflict markers in: {bad}"
```

Notes `[ASSUMED: design recommendation]`:
- `re.MULTILINE` `^` matches after `\n`, so CRLF files work (`\r` follows the marker only on the `=======` line, which is not scanned).
- `uv.lock` is skipped because it is large and generated; add a separate cheap grep in CI if desired.
- The guard also catches markers in `.planning/` docs that quote them verbatim (CONCERNS.md mentions `<<<<<<< HEAD` mid-line inside backticks, which does not match because the regex anchors at line start). Verify that no planning doc has a line that begins with the marker; the earlier scan found none.
- Add a self-test of the regex (e.g. `MARKER.search("<<<<<<< HEAD\nx")` truthy, `MARKER.search("x <<<<<<< y")` falsy) so the guard cannot silently rot. This also satisfies "guard fails if a marker is reintroduced" without needing to dirty the tree.
- Also add a smoke test that `import app.market` works (`importlib.import_module("app.market")`), which covers success criterion 1 permanently.

### CI workflow (FOUND-04, "guard test/CI check")

Recommend both: the pytest guard (runs wherever tests run) plus `.github/workflows/ci.yml` running `uv sync --frozen && uv run pytest` in `backend/` on `push` and `pull_request`. The existing workflows (`claude.yml`, `claude-code-review.yml`) are the only ones, so there is currently no test job. `[VERIFIED: ls .github/workflows]` Use `astral-sh/setup-uv` with Python 3.12 and `working-directory: backend`. Keep it minimal with `permissions: contents: read`. The exact `setup-uv` version tag was not verified this session; the planner should look up the current major tag or install uv with `pip install uv`. `[ASSUMED]`

A cheap extra step before pytest: `! git grep -nE '^(<{7}|>{7})( |$)' -- . ':!uv.lock'`.

### Hygiene files (FOUND-05, FOUND-06)

**`.gitattributes`** (LF for scripts and Docker files, since CRLF breaks `#!/bin/sh` shebangs in the container; PITFALLS.md flags this for Windows hosts):
```
* text=auto
*.sh text eol=lf
Dockerfile text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.ps1 text eol=crlf
```
`*.ps1 eol=crlf` is optional (`[ASSUMED]`; PowerShell handles LF). After adding `* text=auto`, git may warn about renormalization; run `git add --renormalize .` only if the planner wants to normalize the CRLF working files, otherwise skip it to keep the diff small. Safer: omit `* text=auto` and keep only the explicit patterns required by FOUND-06 ("LF for `.sh`, Dockerfile, `.yml`"). Recommended: include only explicit patterns plus `*.py text eol=lf` is NOT required.

**`.dockerignore`**: `.git`, `.github`, `.claude`, `.planning`, `planning`, `independent-reviewer`, `.claude-plugin`, `**/__pycache__`, `**/*.pyc`, `**/.venv`, `**/node_modules`, `frontend/.next`, `frontend/out`, `.env`, `.env.*` with `!.env.example`, `db/*.db`, `test/`, `*.md` except what the build needs (README is not needed). Do not ignore `backend/uv.lock` or `frontend/package-lock.json`.

**`.env.example`** (matches PLAN.md §5 exactly; placeholders only, no real keys; `.env` is already gitignored; `.env.example` is not matched by the `.env` gitignore rule, but verify with `git check-ignore -v .env.example`):
```bash
# OpenRouter API key for LLM chat (required for live AI chat; the rest of the app works without it)
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```
CONCERNS.md notes `MASSIVE_POLL_INTERVAL` is read by `factory.py` but is not in PLAN.md §5. Do not add it to `.env.example` unless the planner decides to document it; the contract says match §5.

**Stale pycache (FOUND-05):** Delete directories `backend/app/api`, `backend/app/chat`, `backend/app/database`, `backend/app/portfolio` (each contains only `__pycache__`), plus `backend/app/__pycache__/main.cpython-312.pyc` and `errors.cpython-312.pyc` per CONCERNS.md. Also present and empty-except-pycache: `backend/tests/api`, `chat`, `database`, `portfolio`; remove those too (they are untracked, gitignored). `[VERIFIED: ls]` Caution: `backend/app/database/` is a path the plan names for real code later, so deleting leaves a clean slate; later phases recreate it. Use `rm -rf` on these exact paths, not a glob.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lockfile editing | Hand-editing `uv.lock` | `uv add` / `uv lock` | Hashes and resolution are generated |
| Finding conflict markers | Custom file walker only | `git ls-files` plus a regex, with a walker fallback | Honours `.gitignore`, avoids scanning `.venv` |
| CRLF normalization | Per-file scripts | `.gitattributes` | Standard, applies on checkout |

## Common Pitfalls

### Pitfall 1: Guard test matches itself
**What goes wrong:** The test file contains the literal marker text and fails permanently.
**How to avoid:** Build the regex from `"<" * 7` fragments as above; never write a line starting with seven `<`.

### Pitfall 2: Deleting too much in `__init__.py`
**What goes wrong:** Removing the whole hunk-2 region also removes `from .simulator import ...` (it appears in both sides) and breaks imports.
**How to avoid:** Keep the "theirs" body of hunk 2 in full; run `python -c "import app.market"` after.

### Pitfall 3: `uv sync` with a stale lock or reintroduced build backend
**What goes wrong:** Reintroducing `[build-system]`/hatchling flips the project from virtual to packaged and invalidates the lock.
**How to avoid:** Keep `[tool.uv] package = false`. CI uses `uv sync --frozen`.

### Pitfall 4: `python` is not on PATH
**What goes wrong:** Verification commands using `python` fail on this Windows machine.
**How to avoid:** Always `cd backend && uv run python -c ...` and `uv run pytest`.

### Pitfall 5: Existing tests may have latent failures
Test health is unverified (they could not import). Budget a triage step: if a test fails after the merge, check whether it is a resolution error (e.g. wrong demo/`__init__` side) before touching tests. Tests were written for the merged code, so failures most likely indicate a resolution mistake. `[ASSUMED]`

### Pitfall 6: CRLF vs LF
Working files are CRLF, git warns "LF will be replaced by CRLF". Editing with tools that rewrite endings creates whole-file diffs. Not a correctness problem; mention in the plan so the executor does not "fix" it with mass reformatting.

### Pitfall 7: Missing system-level tz data
`massive.py` needs `tzdata` at import time on Windows; it is already declared and in the lock. Do not remove it.

## Code Examples

Verification commands (run from `backend/`):
```bash
cd backend
uv run python -c "import app.market as m; print(m.stream_router, m.sync_priced_tickers)"
cd .. && git grep -nE '^(<{7}|>{7})( |$)' ; echo "exit=$? (1 means none found)"
cd backend && uv sync --frozen && uv run pytest -q
```
Note on `git grep` scope: untracked files are not searched; use `git grep --untracked` or the pytest guard.

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| hatchling build backend + wheel packages | virtual uv project (`package = false`) | Matches lock; no build step for an app |
| Conflict markers caught by eye | Guard test plus CI | Prevents recurrence (PITFALLS #2) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Package legitimacy not checked with slopcheck | Package Legitimacy Audit | Low; packages are mandated or already locked |
| A2 | `astral-sh/setup-uv` is the right CI action; version tag unchecked | CI workflow | Workflow fails to start; use `pip install uv` fallback |
| A3 | `.ps1` eol setting and `* text=auto` choices | Hygiene files | Cosmetic |
| A4 | Existing tests pass once markers are resolved correctly | Pitfall 5 | Triage time |
| A5 | litellm 1.105.x exists on PyPI as stated in STACK.md | Standard Stack | `uv add` fails; loosen the range |

## Open Questions

1. **Should the resolved files be committed in this phase?** The researcher was told not to commit. Recommend the plan commit resolution + lock + guard + hygiene files as separate atomic commits after green tests.
2. **Does litellm resolve on Windows with Python 3.12?** Expected yes; `uv add` will show. If resolution fails, report rather than drop the dependency (FOUND-02 requires it).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | sync, lock, pytest | yes | 0.13.0 | — |
| System `python` | — | no (not on PATH) | — | `uv run python` |
| git | guard test file listing, grep | yes | — | rglob fallback in guard |
| Network (PyPI) | `uv add litellm` | assumed yes | — | none; blocks FOUND-02 |
| GitHub Actions | CI | n/a locally; workflow file only | — | pytest guard still works |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 + pytest-asyncio >=0.24 (`asyncio_mode = "auto"`) |
| Config file | `backend/pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`) |
| Quick run command | `cd backend && uv run pytest -x -q` |
| Full suite command | `cd backend && uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | No markers; `import app.market` works | unit (guard + import smoke) | `cd backend && uv run pytest tests/test_baseline.py -q` | Wave 0 (new) |
| FOUND-02 | Deps declared, lock regenerated, sync works | command check | `cd backend && uv lock --check && uv sync --frozen` | n/a (command) |
| FOUND-03 | Market suite passes | existing | `cd backend && uv run pytest tests/market -q` | exists |
| FOUND-04 | Guard fails on marker | unit | `cd backend && uv run pytest tests/test_no_conflict_markers.py -q` | Wave 0 (new) |
| FOUND-05 | Stale dirs gone | command check | `test ! -e backend/app/api && test ! -e backend/app/chat && test ! -e backend/app/database && test ! -e backend/app/portfolio` | n/a |
| FOUND-06 | Files exist | command check | `test -f .gitattributes && test -f .dockerignore && test -f .env.example` | n/a |

For FOUND-02, also assert in a test (optional) that `tomllib` parses `pyproject.toml` and the dependency names include `litellm`, `pydantic`, `python-dotenv`, `tzdata`.

### Sampling Rate
- Per task commit: `cd backend && uv run pytest -x -q`
- Per wave merge: full suite plus the shell checks above
- Phase gate: full suite green, repo-wide marker grep empty, `uv sync --frozen` OK

### Wave 0 Gaps
- [ ] `backend/tests/test_no_conflict_markers.py` (FOUND-04, plus regex self-test)
- [ ] `backend/tests/test_baseline.py` or equivalent: `import app.market` smoke and dependency declaration check (FOUND-01, FOUND-02)
- [ ] `.github/workflows/ci.yml`

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2/V3/V4 | no | No auth in scope |
| V5 Input Validation | no (no new inputs) | — |
| V6 Cryptography | no | — |
| V14 Config / secrets | yes | `.env` stays gitignored; `.env.example` has placeholders only; `.dockerignore` excludes `.env` so secrets are not baked into the image |

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Secret baked into image via build context | Information disclosure | `.dockerignore` excludes `.env` |
| Slopsquatted dependency | Tampering | Review lock diff; `uv sync --frozen` in CI |
| CI with excess permissions | Elevation | `permissions: contents: read` in `ci.yml`; no secrets needed |

## Project Constraints (from CLAUDE.md)
- `planning/PLAN.md` is the binding contract; env vars in `.env.example` must match §5.
- Backend is a uv project in `backend/`; Python 3.12; single worker.
- Dev machine is Windows; use `uv run` rather than bare `python`; Git Bash for shell.
- Do not change market-data behavior in this phase: repair only.

## Sources

### Primary (HIGH)
- Working-tree file reads and greps of `backend/app/market/*.py`, `backend/pyproject.toml`, `backend/uv.lock`, `git diff` (this session)
- `.planning/codebase/CONCERNS.md`, `TESTING.md`, `.planning/research/STACK.md`, `PITFALLS.md`, `.planning/REQUIREMENTS.md`, `planning/PLAN.md`

### Tertiary (LOW)
- CI action names and versions (not looked up)

## Metadata

**Confidence breakdown:**
- Conflict resolution: HIGH (hunks read directly)
- Standard stack: MEDIUM (versions from prior project research; not re-queried)
- Guard/CI design: MEDIUM (recommendation, untested here)
- Hygiene files: MEDIUM (content standard, not executed)

**Research date:** 2026-10-13
**Valid until:** 2026-11-13
