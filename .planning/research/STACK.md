# Stack Research

**Domain:** AI trading workstation (FastAPI + SQLite + SSE, Next.js static export, LiteLLM/OpenRouter, single Docker container)
**Researched:** 2026-10-13
**Confidence:** MEDIUM-HIGH (versions verified against PyPI/npm registries and the Microsoft container registry on 2026-10-13; behavioral gotchas are from registry metadata plus training knowledge and are flagged where unverified)

Scope: the stack in planning/PLAN.md is locked. This file pins versions, config, and supporting libraries only. The existing market-data slice is not re-researched.

## Recommended Stack

### Backend core (Python 3.12, uv)

| Technology | Version (pin as) | Purpose | Why |
|------------|------------------|---------|-----|
| Python | 3.12 (`python:3.12-slim`) | Runtime | Locked. litellm supports `>=3.10,<3.15`, so 3.12 is fine. |
| FastAPI | `>=0.143,<0.144` (locked 0.143.0 in uv.lock) | REST + SSE + static mount | Already locked in the repo. Use `lifespan=` for DB init and background tasks; do not use `@app.on_event`. |
| uvicorn[standard] | `>=0.54` (locked 0.54.0) | ASGI server | Already present. Run a single worker (`--workers 1`). The in-memory PriceCache and the process-wide `asyncio.Lock` require one process. |
| pydantic | `>=2.14,<3` (latest 2.14.1) | Request/response models, LLM structured-output schema | litellm needs `>=2.11` (`>=2.12` on py3.14). Use v2 APIs: `model_validate_json`, `model_json_schema`. |
| sqlite3 (stdlib) | n/a | Persistence | Locked. No aiosqlite and no ORM. See the SQLite config below. |
| litellm | `>=1.105,<1.106` (latest 1.105.0) | LLM call via OpenRouter | Mandated by the cerebras skill. litellm releases very frequently, so pin the minor in `pyproject.toml` and let `uv.lock` hold the exact version. |
| httpx | `>=0.28` (locked 0.28.1) | Massive client | Already present. litellm requires `httpx>=0.28`, which is compatible. |
| python-dotenv | `>=1.2` (latest 1.2.4) | Load `.env` from the project root when running locally | PLAN says the backend reads `.env` from the project root. Docker passes `--env-file`, so there `load_dotenv` is a harmless no-op. Use `load_dotenv(find_dotenv(usecwd=True))` and do not override existing env vars. |
| tzdata | `>=2024.1` (locked 2026.5) | Windows zoneinfo | Already present. |

### Frontend (Next.js static export)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Next.js | `16.4.0` (`engines.node >=20.9.0`) | App framework, `output: 'export'` | Latest stable. The Node 20.9+ requirement is compatible with the locked `node:20-slim` build stage. Turbopack is the default bundler in v16. |
| React / react-dom | `19.3.0` | UI | Next 16 peers `^19`. |
| TypeScript | `~6.0.3` (NOT 7.x) | Types | 7.0.2 is the latest tag (native compiler port). typescript-eslint and the Next lint stack lag new TS majors, so 6.0.x is the safe choice. Moving to 7 can be a later spike. Confidence MEDIUM. |
| Tailwind CSS | `4.3.3` + `@tailwindcss/postcss` `4.3.3` | Styling | v4 is CSS-first: `@import "tailwindcss";` plus an `@theme { --color-accent: #ecad0a; ... }` block in `globals.css`. There is no `tailwind.config.js` by default. Put the dark palette and the `#ecad0a`, `#209dd7`, `#753991` tokens in `@theme`. |
| Recharts | `3.10.1` | Line, sparkline, Treemap | v3 is current and supports React 19 (peer `^19`). Treemap takes a custom `content` renderer, which is how to emit `data-pnl` on each rect. Disable animation on sparklines (`isAnimationActive={false}`) so 500ms ticks don't restart animations. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLite via stdlib `sqlite3` | bundled with Python 3.12 | Single-file DB at `db/finally.db` | Locked. |

SQLite config (training knowledge, MEDIUM; verify with a smoke test):
- Open with `sqlite3.connect(path, check_same_thread=False, isolation_level=None)`. Manage transactions explicitly with `BEGIN IMMEDIATE`/`COMMIT`, which fits the one `asyncio.Lock` per trade rule.
- Run `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;`.
- Call blocking DB code via `asyncio.to_thread` or keep the queries trivially fast. For this data volume, synchronous calls inside short `async def` handlers are acceptable. Do not hold the lock across an `await` on the LLM.
- Use `CREATE TABLE IF NOT EXISTS` in lifespan for idempotent schema creation.
- WAL creates `-wal` and `-shm` sidecar files. This is fine on a Docker named volume, but not on a bind mount on Windows/macOS, which is exactly why PLAN uses a named volume.

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker stage 1 | `node:20-slim` | `npm ci && npm run build` -> `out/` | Locked. Note that Node 20 reached EOL in April 2026. It still builds Next 16 (needs >=20.9), so keep it per the contract. Flag for the user as a later bump to `node:22-slim`. |
| Docker stage 2 | `python:3.12-slim` | Runtime | Locked. |
| uv in image | `COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv` (local uv is 0.13.0) | Dependency install | Pin the uv image tag. Run `uv sync --frozen --no-dev --no-install-project`. Because `[tool.uv] package = false`, no project install is needed. Set `UV_COMPILE_BYTECODE=1`. |
| Playwright image | `mcr.microsoft.com/playwright:v1.64.0-noble` | E2E container in `test/docker-compose.test.yml` | The tag must exactly match the `@playwright/test` version (1.64.0). Pin both, with no caret on the npm side. Use the `-noble` variant (Ubuntu 24.04). `-jammy` also exists. |

### Supporting Libraries (backend)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `>=9` (locked 9.1.1) | Tests | Already in dev group. |
| pytest-asyncio | `>=1.4` (locked 1.4.0) | async tests | Already configured with `asyncio_mode=auto`. |
| respx | `0.23.1` | Mock httpx | Massive client tests. Pre-existing market tests may already cover this; add only if needed. |
| pytest-cov | `7.1.0` | Coverage | Optional. |
| FastAPI `TestClient` (via httpx) | included | API route tests | Needs httpx, which is already present. Use `with TestClient(app):` so lifespan runs. Point `DB_PATH` at `tmp_path` per test. |
| ruff | `0.17.0` | Lint/format | Optional dev tool, single binary. |

### Supporting Libraries (frontend)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| vitest | see Node gotcha | Unit tests for pure logic | Spec requires only pure-logic frontend tests (P&L calc, heatmap colour scale, flash class). |
| @testing-library/react | `16.3.3` | Hook/component tests | Flash-class test. Needs `@testing-library/dom` as an explicit peer. |
| @testing-library/jest-dom | `7.0.1` | Matchers | Optional. |
| jsdom | see Node gotcha | DOM env | For the flash-class test only. Pure logic tests can use `environment: 'node'`. |
| @vitejs/plugin-react | `6.1.2` | JSX transform in vitest | Requires Vite 8 and Node `^20.19 || >=22.12`. |
| @playwright/test | `1.64.0` (exact) | E2E | Lives in `test/`, not `frontend/`. Note Next lists it as an optional peer, so installing it in `frontend/` is unnecessary. |
| eslint + eslint-config-next | eslint `10.x` / config-next `16.4.0` | Lint | Config-next peers `eslint>=9`. Using flat config (`eslint.config.mjs`) is required. Confirm eslint 10 works with config-next before adopting. Otherwise use `^9`. Confidence LOW. |

### Node version gotcha (important)

- vitest 5.0.4 requires Node `^22.12 || ^24 || >=26`, and jsdom 30.x requires `^22.22.2 || ^24.15 || >=26`. The local machine runs Node 26.10 (works), but neither runs on the locked `node:20-slim` image.
- Recommended: run vitest only on the host/dev and CI with Node 22+, never inside the Docker build stage. The Dockerfile build stage only runs `next build`. This keeps `node:20-slim` valid.
- If tests must run on Node 20: use vitest `^4.1` (`engines ^20 || ^22 || >=24`; latest 4.1.9) and jsdom `^29.1`. Check vitest 4's jsdom engine range first. Confidence MEDIUM.
- Add `"engines"` to `frontend/package.json` and a `.nvmrc` so the choice is explicit.

## LiteLLM / OpenRouter specifics (from `.claude/skills/cerebras/SKILL.md`)

```python
from litellm import completion  # or acompletion in async handlers
MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"   # per skill; litellm needs the "openrouter/" prefix
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
```

- **The skill snippet passes `MODEL` without an `openrouter/` prefix.** LiteLLM routes by provider prefix, so a bare `nvidia/...` name will likely fail with a "LLM Provider NOT provided" error. Use `model="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"`. Verify this with a live smoke call in the LLM phase (LOW confidence; the skill is the mandated source but may be incomplete). `OPENROUTER_API_KEY` is read from env automatically.
- Use `await litellm.acompletion(...)` inside FastAPI handlers. The skill's sync `completion` would block the event loop and stall the SSE stream for the whole LLM round-trip. This is the biggest practical gotcha.
- Structured output: `response_format=ChatLLMResponse` (a Pydantic model with `message: str`, `trades: list[Trade]`, `watchlist_changes: list[WatchlistChange]`, all required). Then `ChatLLMResponse.model_validate_json(content)`. On `ValidationError` or `None` content, fall back to the raw text or a generic apology, with no actions (PLAN step 5).
- `reasoning_effort="low"` is per the skill. Pass `extra_body` as shown to pin the Cerebras provider.
- Set `timeout=` (e.g. 30s) and `num_retries=0..1` so a hung free-tier model doesn't hang the UI. Free-tier models return 429s, so map exceptions (`litellm.exceptions.*`) to a friendly chat message rather than a 500.
- Free-model limits: `:free` OpenRouter models have rate and daily caps. This is why `LLM_MOCK=true` should be the default for tests and CI.
- Import cost: `import litellm` is slow (seconds) and heavy. Import it lazily inside the chat module, and not in the mock path, so startup and unit tests stay fast.
- litellm pulls in `openai`, `tiktoken`, `tokenizers`, `aiohttp`, and others. The image grows, so expect a larger layer. Not a concern for this project.

## Next.js static export config

```ts
// next.config.ts
const nextConfig = { output: 'export', images: { unoptimized: true }, trailingSlash: false };
export default nextConfig;
```

- No server features: no route handlers, middleware, `next/image` optimization, or server actions. All data fetching happens in client components (`'use client'`).
- Dev proxy: `next dev` does not serve FastAPI. Use `rewrites()` for local dev only. Rewrites are ignored and cause a warning in `output: 'export'`, so gate them on `NODE_ENV === 'development'`, or simply run FastAPI plus the exported build locally. Alternative: have the dev frontend read `NEXT_PUBLIC_API_BASE`.
- Build output is `frontend/out/`. Copy it to `/app/static` in stage 2. FastAPI mounts `StaticFiles(directory="static", html=True)` after all `/api` routes.
- `EventSource('/api/stream/prices')` is same-origin, so no CORS is needed.
- Use `npm ci` with a committed `package-lock.json`. Set `NEXT_TELEMETRY_DISABLED=1` in the build stage.
- Recharts needs client rendering: mark chart components `'use client'`, and avoid `ResponsiveContainer` measuring at zero size in tests by giving the parent explicit height.

## Installation

```bash
# Backend (from backend/)
uv add "litellm>=1.105,<1.106" "pydantic>=2.14,<3" "python-dotenv>=1.2"
uv add --dev "respx>=0.23" "pytest-cov>=7"

# Frontend (from frontend/)
npm install next@16.4.0 react@19.3.0 react-dom@19.3.0 recharts@3.10.1
npm install -D typescript@~6.0.3 @types/react@19.3.0 @types/node@^20 tailwindcss@4.3.3 @tailwindcss/postcss@4.3.3 \
  vitest@^5 @testing-library/react@16.3.3 @testing-library/dom @testing-library/jest-dom@7.0.1 jsdom@^30 @vitejs/plugin-react@6.1.2

# E2E (from test/)
npm install -D --save-exact @playwright/test@1.64.0
```

`@types/node` is pinned to `^20` to match the build image (latest is 26.x); that mismatch would otherwise type-check APIs unavailable at runtime.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| stdlib sqlite3 | aiosqlite / SQLAlchemy | Only if DB calls become a latency problem. Not needed for single-user volume. |
| Vitest | Jest | Only if Node 20 must run tests and Vitest 4 proves problematic. Vitest is lighter for TS. |
| TypeScript 6.0.x | TypeScript 7.x | After typescript-eslint and Next confirm support. |
| Playwright Docker image (noble) | Installing browsers in an own image | Never; the official image has deps preinstalled. |
| `acompletion` | sync `completion` in `to_thread` | Acceptable fallback if acompletion misbehaves with extra_body. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Sync `litellm.completion` in async handlers | Blocks event loop and freezes the SSE price stream | `litellm.acompletion` |
| `@app.on_event("startup")` | Deprecated | `lifespan` context manager |
| Multiple uvicorn workers / gunicorn | Breaks in-memory PriceCache, the asyncio lock, and duplicates background tasks | One worker |
| Bind-mounting `db/` in Docker on Win/Mac | WAL and permission problems | Named volume `finally-data` (per PLAN) |
| Playwright image tag not matching npm version | Browser binary mismatch causes launch failures | Pin both to 1.64.0 |
| Tailwind v3-style `tailwind.config.js` and `@tailwind base` directives | v4 is CSS-first | `@import "tailwindcss"` + `@theme` |
| Next `rewrites`, middleware, API routes, `next/image` optimizer with `output: export` | Unsupported in static export | Plain client fetch; `images.unoptimized` |
| `pytest-asyncio` event_loop fixture overrides | Removed in 1.x | `asyncio_default_fixture_loop_scope` (already set) |
| `reload`/dev flags in the production CMD | Wasteful and unstable in container | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |

## Stack Patterns by Variant

**If running tests on Node 20:** use vitest 4.1.x and jsdom 29.x.
**If Massive key present:** no stack change; httpx polling only.
**If the uv image or pinned litellm has a security advisory:** bump the minor in `pyproject.toml`; the lockfile is the source of truth in Docker (`--frozen`).

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| next 16.4.0 | node >=20.9, react ^19 | Fine on `node:20-slim` |
| vitest 5.0.4 | node ^22.12 / ^24 / >=26; vite 6.4/7/8 | Not on Node 20 |
| @vitejs/plugin-react 6.1.2 | vite ^8 | Install vite 8 explicitly if vitest does not bring it |
| jsdom 30.x | node ^22.22.2 / ^24.15 / >=26 | Not on Node 20 |
| litellm 1.105.0 | python >=3.10,<3.15; pydantic >=2.11; httpx >=0.28 | OK with current lock |
| recharts 3.10.1 | react ^19 | OK |
| @playwright/test 1.64.0 | image `v1.64.0-noble` | Must match exactly |
| Python 3.12 | all above | Windows dev needs tzdata (present) |

## Repo hygiene notes

- `backend/pyproject.toml` currently has no merge-conflict markers (the stale note in `.planning/codebase/STACK.md` is outdated; git status shows it modified, so re-check `factory.py` as well). Keep `[tool.uv] package = false` and the `testpaths/pythonpath` settings.
- `requires-python = ">=3.12"` is fine locally, but consider `">=3.12,<3.13"` so uv never resolves for 3.13/3.14 differently from the Docker image.

## Sources

- PyPI JSON API (pypi.org/pypi/<pkg>/json), queried 2026-10-13: litellm 1.105.0 (requires_dist, requires_python), pydantic 2.14.1, fastapi 0.143.0, uvicorn 0.54.0, httpx 0.28.1, pytest 9.1.1, pytest-asyncio 1.4.0, python-dotenv 1.2.4, respx 0.23.1, pytest-cov 7.1.0, ruff 0.17.0 (HIGH)
- npm registry (registry.npmjs.org/<pkg>/latest), queried 2026-10-13: next 16.4.0, react 19.3.0, recharts 3.10.1, tailwindcss 4.3.3, typescript 7.0.2 (latest) / 6.0.3, vitest 5.0.4 / 4.1.9, jsdom 30.1.2 / 29.1.1, @vitejs/plugin-react 6.1.2, @playwright/test 1.64.0, engines and peerDependencies fields (HIGH)
- mcr.microsoft.com/v2/playwright/tags/list: `v1.64.0-noble` and `-jammy` tags exist (HIGH)
- `.claude/skills/cerebras/SKILL.md`: mandated LiteLLM call pattern (HIGH for the pattern; the missing `openrouter/` prefix concern is LOW and needs a live check)
- Training knowledge, not re-verified against docs: SQLite pragmas, Next static export restrictions, Tailwind v4 `@theme`, litellm exception handling, TypeScript 7 ecosystem lag (MEDIUM/LOW as flagged)
- Context7 was not consulted (no MCP tools available in this environment).

---
*Stack research for: AI trading workstation*
*Researched: 2026-10-13*
