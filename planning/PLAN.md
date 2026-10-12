# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving        │
│                      (Next.js export)           │
│                                                 │
│  SQLite database (named Docker volume)          │
│  Background tasks: market data, snapshots       │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, persisted via a named Docker volume
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── app/
│       └── database/         # Schema definitions, seed data, initialization logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # SQLite location for local (non-Docker) development
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/app/database/`** contains schema SQL definitions, seed logic and initialization code (see Section 7). It is code only; no database files live here.
- **`db/`** at the top level is where `finally.db` is written when running the backend locally outside Docker. Inside Docker, the same path (`/app/db`) is backed by a named volume instead (see Section 11).
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# OpenRouter API key for LLM chat (required for live AI chat; the rest of the app works without it)
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (see Section 9)
- If `LLM_MOCK` is not `true` and `OPENROUTER_API_KEY` is absent or empty → the app still starts normally. Price streaming, trading and the watchlist all work. `POST /api/chat` returns HTTP 200 with the message "AI chat isn't configured — set OPENROUTER_API_KEY in .env to enable it." and an empty `actions` list.
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Which Tickers Are Priced

The price source tracks the **union of watchlist tickers and tickers with an open position**. Removing a ticker from the watchlist while still holding it keeps it priced, so the position can still be valued and sold. Once it is neither watched nor held, it stops being priced.

### Ticker Validation

- Tickers are uppercased and trimmed, then must match `^[A-Z.]{1,6}$`. Anything else is rejected with `INVALID_TICKER`.
- **Simulator**: any valid-format ticker is accepted. Known tickers start from realistic seed prices. An unknown ticker (e.g. `PYPL`) gets a random seed price between $50 and $300 and default drift/volatility.
- **Massive**: when a ticker is added, the backend checks it against the API. If the API returns no data, the add is rejected with `UNKNOWN_TICKER`.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for all priced tickers (see above) on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- For each ticker the cache holds:
  - `price` — latest price
  - `previous_price` — the price before the latest update
  - `open_price` — the reference for "daily change %". In the simulator this is the first price recorded for the ticker in this server session. With Massive it is the previous day's close from the snapshot response.
  - `timestamp` — when `price` was last updated
- `change_percent` is derived as `(price - open_price) / open_price * 100`
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- The server emits one unnamed `data:` event per ~500ms tick. Each event is a JSON object keyed by ticker:

```json
{
  "AAPL": {
    "ticker": "AAPL",
    "price": 190.12,
    "previous_price": 190.05,
    "open_price": 189.50,
    "change_percent": 0.33,
    "direction": "up",
    "timestamp": "2026-10-12T14:03:21.512Z"
  },
  "MSFT": { "...": "..." }
}
```

- `direction` is `"up"`, `"down"` or `"flat"` (comparing `price` with `previous_price`)
- **On connect**, the first event contains every priced ticker, so the UI fills in at once
- **After that**, each event contains only tickers whose `timestamp` changed since the previous tick. With the simulator that is every ticker; with Massive most ticks are empty and are skipped (no event sent).
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite Initialization at Startup

The backend initializes the database once at app startup, in the FastAPI lifespan hook. If the file doesn't exist or tables are missing, it creates the schema and seeds default data. The same hook then starts the market data task and the snapshot task. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

Every table except `users_profile` has a `user_id` column defaulting to `"default"`. `users_profile` is keyed by its own `id`, which plays the same role. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — the `actions` array returned by `/api/chat`, including each action's status and any error; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

### Trade Execution Rules

Manual trades and LLM-requested trades both go through the same function and follow these rules:

- **Price**: the trade fills at the current cached price. If the ticker has no cached price yet (e.g. just added, before the first Massive poll), the trade is rejected with `NO_PRICE`. The backend never waits for a price.
- **Quantity**: must be > 0. It is rounded to 4 decimal places; anything that rounds to 0 is rejected with `INVALID_QUANTITY`.
- **Cash**: rounded to 2 decimal places after every change.
- **Buys**: require `quantity × price ≤ cash_balance` (otherwise `INSUFFICIENT_CASH`). The new `avg_cost` is the weighted average of the existing position and the new shares.
- **Sells**: require `quantity ≤ held quantity` (otherwise `INSUFFICIENT_SHARES`). `avg_cost` is unchanged. If the remaining quantity is below `1e-6`, the position row is deleted.
- **Buying a ticker that isn't on the watchlist** is allowed. It doesn't add the ticker to the watchlist, but the ticker becomes priced because it is now held.
- **P&L**: only unrealized P&L is tracked and shown. Realized P&L is not stored or displayed; this is intentional.
- **Atomicity**: each trade (cash update, position upsert, trade log insert, snapshot) runs inside a single SQLite transaction, guarded by one process-wide `asyncio.Lock`. This prevents a manual trade and an LLM trade from racing on the cash balance.

---

## 8. API Endpoints

All endpoints return JSON. Money values are dollars rounded to 2 dp; quantities to 4 dp; timestamps are ISO 8601 UTC.

### Errors

Every error response uses one shape:

```json
{"error": "Insufficient cash: need $1,950.30, have $1,200.00", "code": "INSUFFICIENT_CASH"}
```

| Code | HTTP | When |
|---|---|---|
| `INVALID_TICKER` | 400 | Ticker fails format validation |
| `UNKNOWN_TICKER` | 400 | Massive mode: API has no data for the ticker |
| `INVALID_QUANTITY` | 400 | Quantity ≤ 0 or rounds to 0 |
| `INSUFFICIENT_CASH` | 400 | Buy costs more than the cash balance |
| `INSUFFICIENT_SHARES` | 400 | Sell exceeds held quantity (or no position) |
| `NO_PRICE` | 400 | No cached price for the ticker yet |
| `NOT_FOUND` | 404 | Removing a ticker that isn't on the watchlist |

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates (format in Section 6) |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |
| POST | `/api/reset` | Reset to the seed state (see below) |

`GET /api/portfolio`:

```json
{
  "cash_balance": 8049.70,
  "positions_value": 1950.30,
  "total_value": 10000.00,
  "unrealized_pnl": 50.30,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10.0,
      "avg_cost": 190.00,
      "current_price": 195.03,
      "market_value": 1950.30,
      "unrealized_pnl": 50.30,
      "pnl_percent": 2.65
    }
  ]
}
```

`current_price` falls back to `avg_cost` if a held ticker has no cached price yet.

`POST /api/portfolio/trade` request: `{"ticker": "AAPL", "quantity": 10, "side": "buy"}`. Response (200):

```json
{
  "trade": {"id": "…", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 195.03, "executed_at": "…"},
  "portfolio": { "…": "same shape as GET /api/portfolio" }
}
```

`GET /api/portfolio/history`:

```json
{"snapshots": [{"total_value": 10000.00, "recorded_at": "…"}]}
```

`POST /api/reset` clears positions, trades, snapshots and chat messages, restores cash to $10,000 and restores the default watchlist. It returns the fresh `GET /api/portfolio` shape. It is used for demos and to isolate E2E tests.

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

`GET /api/watchlist`:

```json
{
  "tickers": [
    {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "open_price": 189.50,
     "change_percent": 0.33, "direction": "up", "timestamp": "…"}
  ]
}
```

Price fields are `null` for a ticker that hasn't been priced yet.

- `POST /api/watchlist` with `{"ticker": "pypl"}` returns 200 with the single entry in the shape above. It is idempotent: adding a ticker that's already watched returns the existing entry rather than an error.
- `DELETE /api/watchlist/{ticker}` returns 204, or 404 `NOT_FOUND` if the ticker isn't watched.

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |

Request: `{"message": "Buy 10 shares of AAPL and watch PYPL"}`. Response (200):

```json
{
  "message": "Done — buying 10 AAPL and adding PYPL to your watchlist.",
  "actions": [
    {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 195.03, "status": "ok"},
    {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"},
    {"type": "trade", "ticker": "TSLA", "side": "sell", "quantity": 5.0, "status": "error",
     "error": "Insufficient shares: you hold 0 TSLA", "code": "INSUFFICIENT_SHARES"}
  ]
}
```

Failed actions are not HTTP errors. They appear in `actions` with `status: "error"`, and the rest of the actions still run.

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment): `{"status": "ok"}` |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use the `cerebras-inference` skill (in `.claude/skills/cerebras/`) to use LiteLLM via OpenRouter to the `nvidia/nemotron-3-ultra-550b-a55b:free` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the last 20 messages from the `chat_messages` table. Assistant messages include their stored `actions`, so the LLM can see which earlier actions succeeded or failed.
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response and validates it with the Pydantic model. If parsing or validation fails, the raw text (or a generic apology if empty) is returned as `message` with no actions.
6. Auto-executes any trades or watchlist changes specified in the response, in order, recording each one's outcome
7. Stores the user message, and the assistant message with its `actions`, in `chat_messages`
8. Returns `{message, actions}` (shape in Section 8) to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

There is exactly **one LLM call per user message**. The LLM writes its `message` before any action runs, so it doesn't know about failures in this turn. The `actions` array returned by the backend is the source of truth, and the frontend shows each action's result inline. The LLM learns about failures through the history on the next turn.

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (required, may be empty): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (Section 7, Trade Execution Rules)
- `watchlist_changes` (required, may be empty): Array of watchlist modifications; `action` is `"add"` or `"remove"`

All three fields are required so the schema works with strict structured-output modes; "nothing to do" is an empty array.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), it is reported in `actions` with `status: "error"` and shown inline in the chat, as described above.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Phrase trade confirmations as intent ("Buying 10 AAPL…"), since execution results are shown separately
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

The mock matches the user's message (case-insensitive) against these patterns, uses the **first** match, and then runs the result through the normal execution path:

| Pattern | Result |
|---|---|
| `buy <qty> <TICKER>` | `message: "Mock: buying <qty> <TICKER>."`, one buy trade |
| `sell <qty> <TICKER>` | `message: "Mock: selling <qty> <TICKER>."`, one sell trade |
| `add <TICKER>` or `watch <TICKER>` | `message: "Mock: adding <TICKER> to your watchlist."`, one watchlist add |
| `remove <TICKER>` | `message: "Mock: removing <TICKER> from your watchlist."`, one watchlist remove |
| anything else | `message: "Mock: I'm FinAlly, your AI trading assistant."`, no actions |

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change % (`change_percent` from the stream, i.e. change since `open_price`), and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by unrealized P&L % (`pnl_percent`): green = profit, red = loss, neutral gray at 0%, reaching full saturation at ±10% (clamped beyond that). Each rectangle carries a `data-pnl` attribute with its `pnl_percent`, for testing.
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill. Error messages from the API are shown next to the trade bar.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Each entry in the response's `actions` is shown inline as a confirmation (status `ok`) or an error (status `error`, with its message).
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Data Flow

- **Price history**: one per-ticker price history store on the client, filled from the SSE stream since page load. It feeds both the watchlist sparklines and the main chart. There is no price-history API endpoint.
- **Portfolio**: fetched from `GET /api/portfolio` on load, and replaced after each trade (the trade response includes the updated portfolio), after each chat response with any `ok` actions, and after a reset.
- **Live values**: the header total, positions table and heatmap recompute current prices, market values and P&L on the client from the last portfolio response plus live SSE prices. They don't poll the API.
- **Watchlist**: fetched from `GET /api/watchlist` on load and after add/remove (manual or via chat); live prices come from SSE.
- **P&L chart**: fetched from `GET /api/portfolio/history` on load and after each trade.

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`. Map its state to the status dot: `OPEN` → green, `CONNECTING` → yellow, `CLOSED` → red.
- Use **Recharts** for all charts (line, sparkline, treemap). It renders SVG, which is fast enough at this data volume and easy to assert on in Playwright.
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export in out/)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000. The static files are mounted **after** all `/api` routes are registered, at `/`, using `StaticFiles(directory="static", html=True)`, so `/` serves `index.html` and the mount doesn't shadow the API.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The backend writes `finally.db` to `/app/db`, which is backed by the `finally-data` volume. A named volume (not a bind mount of the project's `db/` folder) is used to avoid file-permission problems on Windows and macOS.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, unknown tickers get a seed price, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, weighted average cost, P&L calculations, rounding, edge cases (selling more than owned, buying with insufficient cash, selling at a loss, selling the whole position, no cached price)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow, mock-mode pattern matching
- API routes: correct status codes, response shapes, error codes, reset

**Frontend (React Testing Library or similar)** — pure logic only; UI flows are covered by E2E:
- Portfolio display calculations (live market value, P&L, total value from portfolio + SSE prices)
- Heatmap colour scale (clamping at ±10%, gray at 0)
- Price flash class is triggered on up/down price changes

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism. Each test calls `POST /api/reset` first so tests are independent.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors (via `data-pnl` and fill), P&L chart has data points
- AI chat (mocked): send "buy 1 AAPL", receive the mock response, trade execution appears inline
- SSE resilience: the status dot is green while streaming; after a page reload it returns to green and prices resume updating
