---
phase: 01-repair-baseline
reviewed: 2026-10-13T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - .dockerignore
  - .env.example
  - .gitattributes
  - .github/workflows/ci.yml
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
  - backend/pyproject.toml
  - backend/tests/test_baseline.py
  - backend/tests/test_no_conflict_markers.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-13
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

The conflict resolution is clean: no markers remain, pyproject.toml is valid TOML, and `__all__` is sorted and matches the imports. The new guard test and the CI grep are consistent with each other. `.env.example` matches PLAN.md §5. I found no blockers. The warnings are an unvalidated env float in `factory.py`, a gap in the new `cache.py` timestamp-monotonicity logic, and a CI guard that can pass when `git grep` itself errors.

## Structural Findings (fallow)

None provided.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: MASSIVE_POLL_INTERVAL accepts nan/inf, so the floor does not hold

**File:** `backend/app/market/factory.py:21-24`
**Issue:** `float("nan")` and `float("inf")` both parse without a `ValueError`. `max(nan, 2.0)` returns `nan`, because `2.0 > nan` is False, so the floor is bypassed. `asyncio.sleep(nan)` behaves unpredictably, and `inf` stalls the poller forever with no log line. A non-positive value is handled correctly by `max`.
**Fix:**
```python
import math
try:
    interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
except ValueError:
    interval = 15.0
if not math.isfinite(interval):
    interval = 15.0
interval = max(interval, MIN_POLL_INTERVAL)
```

### WR-02: The monotonic-timestamp guard only covers the implicit-timestamp path

**File:** `backend/app/market/cache.py:38-42`
**Issue:** The `prev.timestamp + 1us` bump runs only when `timestamp is None`. The SSE stream (`stream.py:33`) detects changes with `sent.get(t) != u.timestamp`. The simulator tick passes an explicit `now` (`simulator.py:157-159`), so the guard does not run on the hot path. Its only implicit caller is `_seed`, which runs at start and on add.
- If a caller passes an explicit timestamp equal to the previous one, the price changes but the update is silently never pushed to clients.
- Examples are a frozen test clock, or `_seed` followed by a tick on a coarse clock.
- If `timestamp` is naive and `prev.timestamp` is aware, the comparison would raise `TypeError`, but that only matters for a misuse.

**Fix:** Apply the guard to both paths, or document that explicit timestamps are the caller's responsibility.
```python
ts = timestamp or datetime.now(timezone.utc)
if prev and ts <= prev.timestamp and timestamp is None:
    ts = prev.timestamp + timedelta(microseconds=1)
```
At a minimum, add a test for same-explicit-timestamp updates.

### WR-03: The CI marker check passes if `git grep` itself fails

**File:** `.github/workflows/ci.yml:23`
**Issue:** `! git grep ...` inverts every non-zero exit. A `git grep` error (exit 128, for example a bad pathspec) is turned into success. Exit 1 means "no matches" and exit 0 means "matches found", and only these two are meaningful here. The pytest guard backs this up, but the CI step alone can give a false green.
**Fix:**
```yaml
run: |
  if git grep -nE '^(<{7}|>{7})( |$)' -- . ':!backend/uv.lock'; then
    echo "conflict markers found"; exit 1
  fi
```
This still treats exit 128 as a pass. To fail on a real error, capture `rc=$?` and fail unless it equals 1.

## Info

### IN-01: factory.py is missing `from __future__ import annotations`

**File:** `backend/app/market/factory.py:1`
**Issue:** Every other module in the package starts with this import, which is the project convention. `tickers.py` and `__init__.py` also lack it but have no annotations that need it.
**Fix:** Add the import.

### IN-02: `normalize_ticker` accepts Unicode that case-folds into the ASCII set

**File:** `backend/app/market/tickers.py:25`
**Issue:** `str.upper()` runs before the regex check. Inputs such as `"ﬁ"` (becomes `FI`) or dotless `"ı"` (becomes `I`) are accepted and normalised. This is a minor leniency against the "uppercased and trimmed" spec.
**Fix:** Check `raw.strip().isascii()` before `upper()`.

### IN-03: `_fetch_grouped` can yield an epoch-0 timestamp

**File:** `backend/app/market/massive.py:309`
**Issue:** If every result lacks `t`, `max(r.get("t", 0) ...)` gives 0, so the cache timestamp becomes 1970-01-01.
**Fix:** Fall back to the target day's close time, or to `datetime.now(timezone.utc)`, when the max is 0.

### IN-04: `MassiveDataSource` cannot be restarted after `stop()`

**File:** `backend/app/market/massive.py:142-152`
**Issue:** `stop()` closes the owned client and sets `_closed`. A later `start()` creates a new task that uses the closed client, and every request then fails.
**Fix:** Document it as one-shot, or recreate the client in `start()`.

### IN-05: CI hygiene

**File:** `.github/workflows/ci.yml:3-6, 15-17`
**Issue:** `on: push:` and `on: pull_request:` with no filters run the job twice for PR branches. Actions are pinned to mutable tags. Please confirm that `astral-sh/setup-uv@v10` is an existing tag.
**Fix:** Limit `push` to `branches: [main]`. Pin actions to SHAs if supply-chain hardening matters.

### IN-06: The litellm pin is very tight

**File:** `backend/pyproject.toml:10`
**Issue:** `litellm>=1.105,<1.106` blocks every patch release through resolver constraints. The `uv.lock` already gives reproducibility, and `--frozen` in CI relies on it. `python-dotenv` is declared but has no importer yet, which is fine for a phase-1 declaration.
**Fix:** Use `litellm>=1.105,<2` and rely on the lockfile.

---

_Reviewed: 2026-10-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
