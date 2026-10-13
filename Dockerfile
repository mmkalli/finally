# syntax=docker/dockerfile:1

# ---------- Stage 1: build the Next.js static export ----------
FROM node:20-slim AS frontend

WORKDIR /frontend
ENV NEXT_TELEMETRY_DISABLED=1

# Install dependencies first so this layer is cached until the lockfile changes
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

WORKDIR /app

# Dependencies only (cached until pyproject.toml / uv.lock change)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code, then install the project itself
COPY backend/ ./
RUN uv sync --frozen --no-dev

# Static frontend served by FastAPI at /
COPY --from=frontend /frontend/out ./static

# SQLite lives here; back it with the `finally-data` named volume
RUN mkdir -p /app/db
VOLUME ["/app/db"]

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
