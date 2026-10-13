---
phase: 01-repair-baseline
plan: 03
subsystem: backend-dependencies
tags: [uv, litellm, pydantic, python-dotenv, lockfile]
requires: [01-01]
provides: [declared runtime deps, regenerated uv.lock, baseline smoke test]
affects: [phase-02, phase-03]
key-files:
  created: [backend/tests/test_baseline.py]
  modified: [backend/pyproject.toml, backend/uv.lock]
decisions:
  - "litellm pinned >=1.105,<1.106; pydantic >=2.14,<3; python-dotenv >=1.2"
  - "Project stays virtual (tool.uv.package = false, no build-system)"
metrics:
  completed: 2026-10-13
  tasks: 2
  files: 3
---

# Phase 1 Plan 03: Dependencies and Lock Summary

Declared litellm, pydantic and python-dotenv (plus existing tzdata) as runtime deps, regenerated `uv.lock` (litellm 1.105.0 resolved, 75 packages total, 43 newly added), and added a permanent baseline test.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Package legitimacy check: approved by developer (via orchestrator) | n/a |
| 2 (RED) | Baseline import and dependency tests | 562c1c5 |
| 2 (GREEN) | uv add deps, regenerate lock | 5715f23 |

## Verification

- `uv lock --check` OK; `uv sync --frozen` OK
- `uv run --frozen pytest -q`: 56 passed (53 baseline + 3 new)
- RED run: test_runtime_dependencies_declared failed as expected, other two passed
- No `build-system` in pyproject.toml; `package = false` retained

## Deviations from Plan

None - plan executed as written.

## Known Stubs

None.

## Self-Check: PASSED
