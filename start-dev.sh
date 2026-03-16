#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but not installed."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not installed."
  exit 1
fi

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

echo "Starting FleetWarden API on http://localhost:8000 ..."
(
  cd "$BACKEND_DIR"
  UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
PIDS+=("$!")

echo "Starting FleetWarden worker ..."
(
  cd "$BACKEND_DIR"
  UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run fleetwarden-worker
) &
PIDS+=("$!")

echo "Starting FleetWarden frontend on http://localhost:5173 ..."
(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 0.0.0.0
) &
PIDS+=("$!")

echo
echo "FleetWarden dev stack is starting."
echo "Frontend: http://localhost:5173"
echo "API:      http://localhost:8000"
echo
echo "Press Ctrl+C to stop all processes."

wait

