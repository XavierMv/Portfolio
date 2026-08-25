#!/usr/bin/env bash
# Portfolio Analyzer Discovery — Linux/macOS/Codespaces launcher.
# Windows users: use start.bat instead.
set -euo pipefail
cd "$(dirname "$0")"

# Build the frontend only if it has never been built (or was cleaned).
if [ ! -f frontend/dist/index.html ]; then
  echo "[1/2] Building frontend (first run only)…"
  (cd frontend && npm ci && npm run build)
else
  echo "[1/2] Frontend already built — skipping."
fi

# Stop a previous instance so re-running this script is always safe.
if pgrep -f "uvicorn server:app" >/dev/null 2>&1; then
  echo "      Stopping previous server…"
  pkill -f "uvicorn server:app" || true
  sleep 1
fi

echo "[2/2] Starting server on http://localhost:8000"
cd backend
exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
