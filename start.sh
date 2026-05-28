#!/usr/bin/env bash
# Production mode: build the frontend, then serve everything from one FastAPI
# process (backend serves the built SPA + API on the same port). This is what
# you'd run on the always-on home server / Pi.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

echo "Building frontend…"
(cd frontend && npm run build)

echo "Serving on http://0.0.0.0:$PORT"
exec .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port "$PORT"
