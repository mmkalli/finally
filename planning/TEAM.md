# Agent Team — Ownership & Internal Contracts

PLAN.md is the product spec. This file fixes the *internal* seams so the team can build in parallel.
If you need to change a contract here, edit this file and message the affected owners.

## Team & ownership

| Agent | Owns (writes) | Notes |
|---|---|---|
| `backend` (Backend API engineer) | `backend/app/main.py`, `backend/app/api/`, `backend/app/portfolio/`, `backend/app/market/` (merge fix), `backend/pyproject.toml`, `backend/uv.lock` | lifespan, routes, error shape, trade execution, snapshot task, static mount |
| `database` (Database engineer) | `backend/app/database/`, `backend/tests/database/` | schema, seed, init, connection, data-access functions |
| `llm` (LLM engineer) | `backend/app/chat/`, `backend/tests/chat/` | prompt, LiteLLM call, structured output, mock mode, action execution |
| `frontend` (Frontend engineer) | `frontend/` | Next.js static export, Tailwind, Recharts |
| `devops` (DevOps engineer) | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/`, `.env.example`, root `.gitignore` | |
| `tester` (Integration tester) | `test/` | Playwright E2E + `test/docker-compose.test.yml` |

Only edit files you own. Need a change elsewhere? Message the owner. Need a new dependency in
`backend/pyproject.toml`? Message `backend` (it's the only one running `uv add`).
Do **not** `git commit` — the lead commits. Do not touch `.claude/`.

## Backend package layout

```
backend/app/
  main.py              # FastAPI app + lifespan (backend)
  errors.py            # AppError + handler (backend)
  api/                 # routers: portfolio, watchlist, chat, health, reset (backend)
  portfolio/service.py # execute_trade, get_portfolio, watchlist add/remove, reset (backend)
  database/            # (database)
  chat/                # (llm)
  market/              # existing; stream_router, PriceCache, sources (backend fixes merge)
```

Run from `backend/`: `uv run pytest`, `uv run uvicorn app.main:app --port 8000`.

## Contract: errors (`app/errors.py`, backend)

```python
class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400): ...
```
Codes per PLAN.md §8. A handler renders `{"error": message, "code": code}`.
Extra codes beyond PLAN.md §8:
- `INVALID_SIDE` (400): trade `side` isn't `buy` or `sell`.
- `INVALID_REQUEST`: 422 for a malformed or unparseable request body (FastAPI `RequestValidationError`); 400 for an empty or non-string chat `message`.
Sells check `INSUFFICIENT_SHARES` before `NO_PRICE`. `POST /api/reset` records one $10,000.00 snapshot, so `/api/portfolio/history` right after a reset holds exactly one point.
`InvalidTickerError` / `UnknownTickerError` from `app.market.tickers` are mapped to the same shape.

## Contract: database (`app/database/`, database)

- DB path: env `FINALLY_DB_PATH`, default `<repo>/db/finally.db` (in Docker `/app/db/finally.db`).
- `init_db(path=None) -> None` — create schema if missing, seed if empty. Idempotent.
- `get_connection() -> sqlite3.Connection` — one shared connection, `check_same_thread=False`,
  `row_factory = sqlite3.Row`, WAL, foreign keys on. Tests can call `init_db(":memory:")` or a tmp path.
- `transaction(conn)` — context manager: `BEGIN IMMEDIATE` … commit / rollback.
- Data access (all take `conn` first, `user_id="default"` last, return plain dicts/lists, timestamps ISO-8601 UTC with `Z`):
  - `get_cash(conn)`, `set_cash(conn, amount)`
  - `list_watchlist(conn) -> list[str]` (ordered by `added_at`), `add_watchlist(conn, ticker) -> bool` (False if already present), `remove_watchlist(conn, ticker) -> bool`
  - `list_positions(conn) -> list[dict]` (ticker, quantity, avg_cost, updated_at), `get_position(conn, ticker) -> dict | None`, `upsert_position(conn, ticker, quantity, avg_cost)`, `delete_position(conn, ticker)`
  - `insert_trade(conn, ticker, side, quantity, price) -> dict` (id, ticker, side, quantity, price, executed_at)
  - `insert_snapshot(conn, total_value)`, `list_snapshots(conn) -> list[dict]` (total_value, recorded_at, ascending)
  - `insert_chat_message(conn, role, content, actions: list | None)`, `recent_chat_messages(conn, limit=20) -> list[dict]` (chronological; `actions` decoded from JSON)
  - `reset_user(conn)` — clear positions/trades/snapshots/chat, cash 10000, default watchlist
- These functions do NOT commit; callers wrap in `transaction(conn)`.
- Extras / details: everything is importable from `app.database`. `close_db()`; `default_db_path()`;
  `now_iso()`; `transaction` nests (inner joins outer). `get_cash` raises `KeyError` if no profile.
  `set_cash` and `insert_snapshot` round to 2 dp; `upsert_position` stores values as given.
  `list_positions` is ordered by ticker. `recent_chat_messages` items: `role, content, actions, created_at`.
  `init_db` reseeds only when the profile row is missing (an emptied watchlist stays empty across restarts).
  Default path: `<repo>/db/finally.db` locally; when the backend dir isn't named `backend` (Docker `/app`) → `/app/db/finally.db`.
- `app.market.priced.load_priced_tickers(conn)` already queries `watchlist`/`positions` — keep those table/column names.

## Contract: portfolio service (`app/portfolio/service.py`, backend)

Module-level `trade_lock = asyncio.Lock()`. App state on `app.state`: `conn`, `cache` (PriceCache), `source` (MarketDataSource).

```python
async def execute_trade(conn, cache, source, ticker: str, side: str, quantity: float) -> dict  # trade dict; raises AppError
def get_portfolio(conn, cache) -> dict          # PLAN.md §8 GET /api/portfolio shape
async def add_to_watchlist(conn, cache, source, ticker) -> dict      # watchlist entry shape; raises AppError
async def remove_from_watchlist(conn, cache, source, ticker) -> None # raises AppError NOT_FOUND
```
After any watchlist/position change, call `sync_priced_tickers(conn, source)`.

## Contract: chat (`app/chat/`, llm)

```python
async def handle_chat(conn, cache, source, message: str) -> dict  # {"message": str, "actions": [...]}
```
`backend` mounts `POST /api/chat` and calls this. `llm` executes actions via the portfolio service
functions above and stores messages via the database functions. Mock mode when `LLM_MOCK=true`;
missing `OPENROUTER_API_KEY` → the fixed message from PLAN.md §5. Note: there is currently no `.env`
in the repo, so live calls can't be exercised — rely on mock mode and unit tests with a patched completion.

## Contract: frontend ↔ backend

Exactly PLAN.md §6 and §8. Static export goes to `frontend/out/`; Docker copies it to `backend/static/`
(served at `/` by `StaticFiles(directory="static", html=True)` after all `/api` routes). For local dev,
`next.config` may set rewrites to `http://localhost:8000` in dev only. Testability hooks the E2E suite
relies on — keep these stable `data-testid`s:

`watchlist-row-<TICKER>`, `price-<TICKER>`, `header-total-value`, `header-cash`, `connection-status`
(with `data-status="open|connecting|closed"`), `trade-ticker`, `trade-quantity`, `trade-buy`, `trade-sell`,
`trade-error`, `watchlist-add-input`, `watchlist-add-button`, `watchlist-remove-<TICKER>`,
`position-row-<TICKER>`, `heatmap` (rects carry `data-pnl`), `pnl-chart`, `chat-input`, `chat-send`,
`chat-message` (each message), `chat-action` (each action, with `data-status="ok|error"`), `main-chart`
(with `data-ticker="<selected ticker>"`). The E2E suite also reads the positions table quantity from the
2nd `<td>` of `position-row-<TICKER>`, and heatmap colour from the `fill` of the `[data-pnl]` element (or its `rect`/`path`).

**Gotcha:** root `.gitignore` ignores `lib/` — don't put frontend code in `frontend/src/lib/` (use `src/utils/` or similar), or ask `devops` to scope the rule to Python.
