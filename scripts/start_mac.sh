#!/usr/bin/env bash
# Start FinAlly in Docker (macOS/Linux). Safe to run repeatedly.
#
# Usage: ./scripts/start_mac.sh [--build] [--no-open]
#   --build    rebuild the image even if it already exists
#   --no-open  don't open the browser
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
VOLUME="finally-data"
PORT="${FINALLY_PORT:-8000}"
URL="http://localhost:${PORT}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD=0
OPEN=1
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

if [[ "$BUILD" == 1 ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
fi

# Replace any existing container (running or stopped); the volume is kept
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Removing existing container '$CONTAINER'..."
  docker rm -f "$CONTAINER" >/dev/null
fi

ENV_ARGS=()
if [[ -f .env ]]; then
  ENV_ARGS=(--env-file .env)
else
  echo "Note: no .env file found, starting without one (simulator data, AI chat disabled)."
  echo "      To configure: cp .env.example .env  and set OPENROUTER_API_KEY, then rerun."
fi

docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  -v "${VOLUME}:/app/db" \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} \
  "$IMAGE" >/dev/null

echo -n "Waiting for FinAlly to start"
for _ in $(seq 1 60); do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    echo " ready."
    break
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]]; then
    echo
    echo "Container exited. Logs:" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
  fi
  echo -n "."
  sleep 1
done

echo "FinAlly is running at ${URL}"
echo "Stop it with ./scripts/stop_mac.sh (your data is kept in the '${VOLUME}' volume)."

if [[ "$OPEN" == 1 ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
