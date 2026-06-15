#!/usr/bin/env bash
# Build the React SPA into backend/app/static/ for single-process production
# serving by FastAPI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [ ! -d node_modules ]; then
  echo "==> Installing frontend deps"
  npm install
fi

echo "==> Building SPA -> backend/app/static/"
npm run build

echo "==> Built. Run the backend with:"
echo "      cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
