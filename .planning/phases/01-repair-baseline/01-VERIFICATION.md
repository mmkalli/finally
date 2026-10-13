---
phase: 01-repair-baseline
verified: 2026-10-13T00:00:00Z
status: human_needed
score: 5/5 must-haves verified (CI green run pending)
overrides_applied: 0
human_verification:
  - test: "Push branch and confirm .github/workflows/ci.yml passes on GitHub"
    expected: "Marker grep, uv sync --frozen and pytest steps all green on ubuntu-latest"
    why_human: "CI has not run yet (nothing pushed); cannot be verified locally"
---

# Phase 1: Repair & Baseline Verification Report

**Goal:** The existing market-data code imports, its tests pass, and the repo is protected against regressing to a broken state
**Status:** human_needed (all local checks pass; only the first GitHub CI run remains)

## Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `import app.market` succeeds, no conflict markers in repo | VERIFIED | `uv run --frozen python -c "import app.market"` printed ok; a line-start marker grep (excluding .claude and node_modules) returned no files; `factory.py` is tracked |
| 2 | `uv sync` works from regenerated lock with litellm, pydantic, python-dotenv, tzdata | VERIFIED | pyproject.toml declares all four and is valid TOML; `uv sync --frozen` ran ("Checked 73 packages"); uv.lock has all four packages |
| 3 | `uv run pytest` passes full market suite | VERIFIED | `uv run --frozen pytest -q` gave 59 passed |
| 4 | Guard fails if a marker is reintroduced | VERIFIED | `backend/tests/test_no_conflict_markers.py` scans git-tracked and untracked files with a tested regex (positive and negative cases); the CI step also runs `git grep` for markers. Whether CI itself is green is a human item |
| 5 | `.gitattributes`, `.dockerignore`, `.env.example` exist; stale pycache gone | VERIFIED | All three are tracked in git. `.gitattributes` sets LF for sh, Dockerfile, yml and yaml. The only `__pycache__` dirs are under `app/`, `app/market/`, `tests/` and `tests/market/`; none for api, chat, database or portfolio |

**Score:** 5/5

## Requirements Coverage

| Req | Status | Evidence |
|-----|--------|----------|
| FOUND-01 | SATISFIED | Truth 1 |
| FOUND-02 | SATISFIED | Truth 2 |
| FOUND-03 | SATISFIED | Truth 3 |
| FOUND-04 | SATISFIED (CI run pending) | Truth 4 |
| FOUND-05 | SATISFIED | Truth 5 |
| FOUND-06 | SATISFIED | Truth 5 |

All six IDs appear in REQUIREMENTS.md mapped to Phase 1; no orphaned requirements.

## Anti-Patterns

No TBD, FIXME or XXX markers in `backend/app` or `backend/tests`. The review's 3 advisory warnings (01-REVIEW.md) do not break any must-have:
- WR-01: `MASSIVE_POLL_INTERVAL` accepts nan/inf, so the floor can be bypassed.
- WR-02: the monotonic-timestamp guard in `cache.py` only covers the implicit-timestamp path.
- WR-03: the CI marker guard can pass if `git grep` itself errors.

These are worth fixing in a later phase.

## Human Verification Required

1. **First CI run:** push the branch and confirm the `ci` workflow is green. Expected: all steps pass.

## Gaps Summary

No gaps. Remaining item is the first green CI run on GitHub.

_Verifier: Claude (gsd-verifier)_
