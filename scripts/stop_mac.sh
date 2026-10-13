#!/usr/bin/env bash
# Stop and remove the FinAlly container (macOS/Linux). Safe to run repeatedly.
# The finally-data volume is kept, so your portfolio survives the next start.
set -euo pipefail

CONTAINER=finally

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed; nothing to stop."
  exit 0
fi

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null
  echo "FinAlly stopped. Data is kept in the 'finally-data' volume."
else
  echo "FinAlly is not running."
fi
