#!/usr/bin/env bash
# Start FinAlly in Docker (macOS/Linux). Safe to run repeatedly.
#
#   ./scripts/start_mac.sh            # build the image if missing, then (re)start the container
#   ./scripts/start_mac.sh --build    # rebuild the image first
#   ./scripts/start_mac.sh --no-open  # don't open a browser
set -euo pipefail

IMAGE=finally
CONTAINER=finally
VOLUME=finally-data
PORT="${FINALLY_PORT:-8000}"
URL="http://localhost:${PORT}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

build=false
open_browser=true
for arg in "$@"; do
  case "$arg" in
    --build) build=true ;;
    --no-open) open_browser=false ;;
    -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Get it from https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop (or the docker daemon) and try again." >&2
  exit 1
fi

if $build || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building the $IMAGE image (the first build takes a few minutes)..."
  docker build -t "$IMAGE" "$ROOT"
fi

# Replace any existing container so a new image or .env takes effect. The data lives in the volume.
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null
fi

env_args=()
if [ -f "$ROOT/.env" ]; then
  env_args=(--env-file "$ROOT/.env")
else
  echo "No .env found: running with the market simulator and AI chat off."
  echo "To enable chat: cp .env.example .env, then add your OPENROUTER_API_KEY."
fi

docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  -v "${VOLUME}:/app/db" \
  ${env_args[@]+"${env_args[@]}"} \
  "$IMAGE" >/dev/null

printf "Waiting for FinAlly to start"
ready=false
for _ in $(seq 1 30); do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    ready=true
    break
  fi
  if [ "$(docker container inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    break
  fi
  printf "."
  sleep 1
done
echo

if ! $ready; then
  echo "FinAlly did not become healthy. Recent logs:" >&2
  docker logs --tail 40 "$CONTAINER" >&2 || true
  exit 1
fi

echo "FinAlly is running at $URL"
echo "Stop it with ./scripts/stop_mac.sh (your data is kept in the '$VOLUME' volume)."

if $open_browser; then
  if command -v open >/dev/null 2>&1; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
