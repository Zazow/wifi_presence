# syntax=docker/dockerfile:1

# ---- Stage 1: build the React/Vite frontend ----
FROM node:20-alpine AS frontend
WORKDIR /frontend
# Install deps from the lockfile first (better layer caching).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /frontend/dist

# ---- Stage 2: Python runtime that serves the API + built SPA ----
FROM python:3.13-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Persist the database in the /data volume (survives image updates).
    WIFI_PRESENCE_DB=/data/wifi_presence.db

# Backend deps (amd64/arm64 wheels exist for paramiko/cryptography — no compiler needed).
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + the built frontend (app.py serves ../frontend/dist).
COPY backend/ backend/
COPY --from=frontend /frontend/dist frontend/dist

VOLUME ["/data"]
EXPOSE 8000

# Liveness: hit /healthz (no curl in slim image, so use Python).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz', timeout=4)" || exit 1

# PORT is overridable (e.g. if 8000 is taken on the host).
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
