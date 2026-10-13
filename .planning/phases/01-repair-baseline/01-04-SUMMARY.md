---
phase: 01-repair-baseline
plan: 04
subsystem: ci-guard
tags: [pytest, github-actions, conflict-markers, uv]
requires: [01-01, 01-02, 01-03]
provides: [conflict-marker regression guard, CI workflow]
affects: [all future phases]
key-files:
  created: [backend/tests/test_no_conflict_markers.py, .github/workflows/ci.yml]
  modified: []
decisions:
  - "setup-uv pinned to major tag v10 (latest release v10.3.0 confirmed via gh api)"
metrics:
  completed: 2026-10-13
  tasks: 2
  files: 2
---

# Phase 1 Plan 04: Conflict-Marker Guard and CI Summary

A pytest guard scans every non-ignored repo file for line-start seven-character conflict markers, and a GitHub Actions workflow runs the same grep, `uv sync --frozen` and the backend tests on push and pull_request.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Conflict-marker guard test with regex self-test | d8e2dd3 |
| 2 | CI workflow and phase gate | 248530d |

## Verification

- Probe proof: with untracked `backend/tests/_tmp_marker_probe.txt` present (first line a seven-`<` marker plus " HEAD"), `test_no_conflict_markers` FAILED listing `backend/tests/_tmp_marker_probe.txt` (1 failed, 2 passed). After deleting the probe, 3 passed. The probe file no longer exists.
- Phase gate: `uv sync --frozen` OK; `uv run --frozen pytest -q` gives 59 passed; repo-wide `git grep --untracked` marker check prints nothing (exit 1); ci.yml parses as YAML; no `pull_request_target` or `secrets.`; `backend/app/api` absent, `.gitattributes`, `.dockerignore`, `.env.example` present.

## Deviations from Plan

- setup-uv version: the plan suggested `@v6` with an option to use a newer major. `gh api` reported v10.3.0 as latest, so the workflow uses `astral-sh/setup-uv@v10`.
- The run was interrupted once by an API rate limit and resumed; no work was lost.

## Known Stubs

None.

## Manual Follow-up

Push to GitHub to see the CI job run (manual-only row in 01-VALIDATION.md); not pushed here.

## Self-Check: PASSED
