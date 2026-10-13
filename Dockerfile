# FinAlly: one container, one port (PLAN.md §11).
#   docker build -t finally .
#   docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally

# ---- Stage 1: static Next.js export -----------------------------------------
FROM node:20-slim AS frontend

WORKDIR /frontend
ENV NEXT_TELEMETRY_DISABLED=1

# Dependencies first, so source edits don't reinstall node_modules
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---- Stage 2: FastAPI runtime ------------------------------------------------
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /usr/local/bin/

# Use the image's Python, compile bytecode once at build time
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Mirrors the repo layout: app/main.py resolves static/ and the default db/ from it
WORKDIR /app/backend

# Dependencies first, so code edits reuse this layer
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --locked --no-dev

COPY --from=frontend /frontend/out ./static

# Non-root user. A fresh named volume copies /app/db's ownership from the image.
RUN useradd --uid 1000 --no-create-home --home-dir /app finally \
    && mkdir -p /app/db \
    && chown finally:finally /app/db
USER finally

ENV PATH="/app/backend/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db
VOLUME ["/app/db"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Open SSE connections never finish on their own; cap the graceful shutdown so `docker stop` is quick
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "3"]
