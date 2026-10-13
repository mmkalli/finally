---
phase: 01-repair-baseline
plan: 01
subsystem: market-data
tags: [merge-conflict, repair, market]
requires: []
provides:
  - "Conflict-free backend/app/market package; import app.market works"
  - "app.market exports stream_router, load_priced_tickers, sync_priced_tickers"
affects: [01-02, 01-03]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified:
    - backend/app/market/__init__.py
    - backend/app/market/cache.py
    - backend/app/market/demo.py
    - backend/app/market/factory.py
    - backend/app/market/interface.py
    - backend/app/market/massive.py
    - backend/app/market/models.py
    - backend/app/market/seed_data.py
    - backend/app/market/simulator.py
    - backend/app/market/tickers.py
key-decisions:
  - "__init__.py keeps theirs (priced + stream exports); demo.py keeps HEAD (sparkline renderer)"
  - "Per-ticker auto timestamps in PriceCache made strictly increasing"
requirements-completed: [FOUND-01, FOUND-03]
duration: 10min
completed: 2026-10-13
---

# Phase 1 Plan 01: Repair Market Package Summary

Resolved all merge-conflict hunks in the market package (nine modules plus the already-resolved factory.py committed); `import app.market` works and `tests/market` passes (53 tests).

## Tasks
1. Seven one-hunk modules: deleted the 4-line stray hunk each (numstat 0/4 confirmed).
2. `__init__.py` (kept theirs) and `demo.py` (kept HEAD) resolved; import smoke and suite green. Commit 91f5d5b (tasks 1 and 2 committed together, as the plan specifies one commit).

## Deviations from Plan

**1. [Rule 1 - Bug] Windows clock repeats timestamps, breaking SSE change detection**
- **Found during:** Task 2 test run (`test_stream.py::test_first_frame_full_then_only_changes` failed, deterministically)
- **Issue:** Two `PriceCache.update` calls in quick succession got identical `datetime.now()` values on Windows, so `price_events` (which detects change by timestamp) skipped the update.
- **Fix:** In `cache.py`, when the timestamp is auto-generated and not newer than the previous one for that ticker, use previous + 1 microsecond. Explicit timestamps (Massive) are untouched. Tests not edited.
- **Files modified:** backend/app/market/cache.py
- **Commit:** 91f5d5b

Otherwise: plan executed as written.

## Known Stubs
None.

## Self-Check: PASSED
Commit 91f5d5b exists; no conflict markers in backend/app/market; tests/market 53 passed; pyproject.toml, uv.lock and .claude files not staged.
