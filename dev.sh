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

# Best-effort LAN IP so you can open the UI from a phone on the same network.
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
echo "Backend:  http://localhost:$BACKEND_PORT (local only; proxied by the frontend)"
echo "Frontend (this machine): http://localhost:5280"
if [ -n "$LAN_IP" ]; then
  echo "Frontend (phone/LAN):    http://$LAN_IP:5280   <-- open this on your phone"
else
  echo "Frontend (phone/LAN):    see the 'Network:' URL Vite prints below"
fi
wait
