# External Integrations

**Analysis Date:** 2026-10-13

Status legend: **Built** = in the repo. **Planned** = in `planning/PLAN.md` only.

## APIs & External Services

**Market data (Built):**
- Massive (Polygon.io-compatible) REST API - optional real prices, polled (not WebSocket).
  - Client: `httpx.AsyncClient` in `backend/app/market/massive.py`, `BASE_URL = "https://api.massive.com"`
  - Endpoints: `/v2/snapshot/locale/us/markets/stocks/tickers` (snapshot) and `/v2/aggs/grouped/locale/us/market/stocks/{day}` (grouped daily aggregates)
  - Auth: `Authorization: Bearer <MASSIVE_API_KEY>` header; a 401 is logged as an error and no prices stream
  - Poll interval: `MASSIVE_POLL_INTERVAL` (default 15s, min 2s), selected in `backend/app/market/factory.py`
  - Tests use an in-process fake: `backend/tests/market/fake_massive.py`
  - Reference docs: `planning/MASSIVE_API.md`
- Built-in GBM simulator (default, no network): `backend/app/market/simulator.py`, seed prices in `backend/app/market/seed_data.py`.

**LLM (Planned):**
- LiteLLM -> OpenRouter -> Cerebras, model `nvidia/nemotron-3-ultra-550b-a55b:free`, structured outputs. Auth: `OPENROUTER_API_KEY`. No code or dependency yet (`backend/app/chat/` is empty). Mock mode via `LLM_MOCK=true`.

## Data Storage

**Databases:**
- SQLite single file `db/finally.db` (Docker: `/app/db` on volume `finally-data`) - Planned. `backend/app/database/` and `backend/app/portfolio/` contain no source yet.

**In-memory (Built):**
- Shared price cache: `backend/app/market/cache.py` (`PriceCache`), written by the simulator/Massive source, read by SSE in `backend/app/market/stream.py`.

**File Storage:** Local filesystem only.

**Caching:** In-process `PriceCache` only.

## Authentication & Identity

**Auth Provider:** None. Single hardcoded user `"default"` (planned schema); no login.

## Monitoring & Observability

**Error Tracking:** None.

**Logs:** Python stdlib `logging` (`log = logging.getLogger(__name__)`) in `backend/app/market/`.

## CI/CD & Deployment

**Hosting:** Planned Docker container (no Dockerfile yet); optional Render / AWS App Runner.

**CI Pipeline:** GitHub Actions, only Claude tooling (no test/build CI):
- `.github/workflows/claude.yml` - `anthropics/claude-code-action@v1`, secret `CLAUDE_CODE_OAUTH_TOKEN`
- `.github/workflows/claude-code-review.yml` - same action for PR review
- Both on `ubuntu-latest` with `actions/checkout@v4`.

## Environment Configuration

**Required env vars (current code):** none required; optional `MASSIVE_API_KEY`, `MASSIVE_POLL_INTERVAL`.

**Planned:** `OPENROUTER_API_KEY`, `LLM_MOCK`. `.env` is read from project root (gitignored; `.env.example` not yet committed).

**Secrets location:** local `.env` (not inspected); GitHub Actions secrets for `CLAUDE_CODE_OAUTH_TOKEN`.

## Webhooks & Callbacks

**Incoming:** None. Only the SSE endpoint `GET /api/stream/prices` (Built, `backend/app/market/stream.py`) which is client-pull, not a webhook.

**Outgoing:** None.

---

*Integration audit: 2026-10-13*
