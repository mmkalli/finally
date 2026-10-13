---
phase: 1
slug: repair-baseline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-13
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 + pytest-asyncio >=0.24 (`asyncio_mode = "auto"`) |
| **Config file** | `backend/pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`) |
| **Quick run command** | `cd backend && uv run pytest -x -q` |
| **Full suite command** | `cd backend && uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest -x -q` (once the market package imports)
- **After every plan wave:** Run the full suite and the shell checks below
- **Before `/gsd:verify-work`:** The full suite is green, a repo-wide marker grep finds nothing, and `uv sync --frozen` succeeds
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-xx | TBD | TBD | FOUND-01 | — | N/A | unit (import smoke) | `cd backend && uv run pytest tests/test_baseline.py -q` | ❌ W0 | ⬜ pending |
| 1-xx | TBD | TBD | FOUND-02 | T-1-supply | Lock reviewed; frozen sync | command | `cd backend && uv lock --check && uv sync --frozen` | n/a | ⬜ pending |
| 1-xx | TBD | TBD | FOUND-03 | — | N/A | existing suite | `cd backend && uv run pytest tests/market -q` | ✅ | ⬜ pending |
| 1-xx | TBD | TBD | FOUND-04 | — | N/A | unit (guard + regex self-test) | `cd backend && uv run pytest tests/test_no_conflict_markers.py -q` | ❌ W0 | ⬜ pending |
| 1-xx | TBD | TBD | FOUND-05 | — | N/A | command | `test ! -e backend/app/api && test ! -e backend/app/chat && test ! -e backend/app/database && test ! -e backend/app/portfolio` | n/a | ⬜ pending |
| 1-xx | TBD | TBD | FOUND-06 | T-1-secrets | `.env` excluded from Docker context; placeholders only | command | `test -f .gitattributes && test -f .dockerignore && test -f .env.example && grep -q '^\.env$' .dockerignore` | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task IDs are filled in after planning.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_no_conflict_markers.py`: FOUND-04, including a regex self-test
- [ ] `backend/tests/test_baseline.py`: the `import app.market` smoke test and the dependency declaration check (FOUND-01, FOUND-02)
- [ ] `.github/workflows/ci.yml`: runs `uv sync --frozen && uv run pytest` plus a marker grep

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI workflow runs green on GitHub | FOUND-04 | Requires a push to the remote | After pushing the branch, check the Actions tab; the `ci` job passes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
