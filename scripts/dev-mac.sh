#!/usr/bin/env bash
# Run backend (uvicorn :8000) and frontend (vite :5173) concurrently for Mac dev.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d backend/.venv ]; then
  echo "==> Creating backend venv"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --upgrade pip
  backend/.venv/bin/pip install -r backend/requirements-dev.txt
fi

if [ -d frontend ] && [ -f frontend/package.json ] && [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend deps"
  (cd frontend && npm install)
fi

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on :8000"
(cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
pids+=($!)

if [ -d frontend ] && [ -f frontend/package.json ]; then
  echo "==> Starting frontend on :5173"
  (cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
  pids+=($!)
fi

wait
