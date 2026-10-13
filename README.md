# FinAlly — AI Trading Workstation

An AI-powered trading terminal: live streaming prices, a simulated $10k portfolio, and a chat assistant that can analyze your positions and place trades for you. Built entirely by coding agents as the capstone of an agentic AI coding course.

## Features

- Live prices over SSE, with green/red flashes and sparklines
- Market orders with instant fills, fractional shares and no fees
- Portfolio heatmap, P&L chart and positions table
- AI chat (LiteLLM → OpenRouter, Cerebras) that executes trades and edits the watchlist
- Built-in market simulator, or real data through the Massive (Polygon.io) API

## Quick Start

```bash
cp .env.example .env              # add OPENROUTER_API_KEY to enable AI chat
./scripts/start_mac.sh            # Windows: .\scripts\start_windows.ps1
```

Then open http://localhost:8000. Stop it with `./scripts/stop_mac.sh` (or `stop_windows.ps1`). Your data stays in the `finally-data` Docker volume.

Or run Docker directly:

```bash
docker build -t finally .
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

Or with Compose: `docker compose up --build -d` (and `docker compose down`).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Turns on AI chat. Everything else works without it |
| `MASSIVE_API_KEY` | — | Real market data. Leave it empty to use the simulator |
| `LLM_MOCK` | `false` | Returns deterministic chat responses, for tests |

## Stack

One container on port 8000. FastAPI (Python, uv) serves the REST API, the SSE stream and a static Next.js + Tailwind export. Data lives in SQLite, and every chart is drawn with Recharts.

## Layout

```
frontend/   Next.js app (static export)
backend/    FastAPI uv project
planning/   Specs and agent contracts (start with PLAN.md)
scripts/    Start/stop scripts
test/       Playwright E2E tests
```

## Testing

- Backend: `cd backend && uv run pytest`
- E2E: `docker compose -f test/docker-compose.test.yml up`, which runs with `LLM_MOCK=true`

## License

See [LICENSE](LICENSE).
