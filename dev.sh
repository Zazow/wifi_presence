#!/usr/bin/env bash
# Run backend (FastAPI, auto-reload) and frontend (Vite dev server) together.
# Open http://localhost:5280 — Vite proxies /api and the WebSocket to :8000.
# Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${BACKEND_PORT:-8000}"

# First-run convenience: set up deps if missing.
if [ ! -d .venv ]; then
  echo "Creating Python venv and installing backend deps…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend deps…"
  (cd frontend && npm install)
fi

pids=()
cleanup() {
  echo
  echo "Stopping…"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting backend on :$BACKEND_PORT …"
.venv/bin/python -m uvicorn backend.app:app --reload --port "$BACKEND_PORT" &
pids+=($!)

echo "Starting frontend dev server …"
(cd frontend && npm run dev) &
pids+=($!)

echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:5280  <-- open this"
wait
