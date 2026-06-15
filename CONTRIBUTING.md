# Contributing

Thanks for your interest in the Home Dashboard. It's a small, local-only NYC
subway / weather / photos kiosk: a FastAPI backend plus a React + Tailwind SPA,
served by a single Uvicorn process. See [`README.md`](./README.md) for the full
feature tour and [`PLAN.md`](./PLAN.md) for architecture rationale.

## Dev setup

Follow the **Mac development** section of the [README](./README.md#mac-development):

```sh
cp .env.example .env          # all keys optional — defaults work out of the box
./scripts/dev-mac.sh          # uvicorn :8000 + vite :5173 (proxies /api → :8000)
```

You only *need* to edit `.env` if you want a non-default photo directory or
weather location, and even those are editable at runtime through the settings UI
(the gear in the top-right) without restarting.

## Running tests & build

Backend tests (pytest):

```sh
cd backend && .venv/bin/python -m pytest tests/ -q
```

Frontend type-check + production build (must stay clean):

```sh
cd frontend && npm run build      # tsc -b && vite build
```

Please keep both green before opening a PR.

## Code style & conventions

- **Backend**: FastAPI + Pydantic. Routers live in `backend/app/*.py` and are
  included from `main.py`. Keep upstream calls async and cached; preserve the
  stale-on-failure / 503-when-no-cache semantics.
- **Frontend**: React 18 + TypeScript + Tailwind. No router library — the
  settings screen is reached via a hash route. Typed API fetchers live in
  `frontend/src/api.ts`.
- **Layered config** is the core model:
  - `.env` (via `pydantic-settings`) holds **seed defaults** + infra-only keys
    (host, port, cache TTLs, static dir, feed URLs).
  - `settings.json` (gitignored, at the repo root) holds **runtime overrides**
    written by the settings UI. User-tunable fields are always read through
    `config_store.get_runtime_config()`, never the frozen `Settings` singleton.
  - Effective config = defaults deep-merged with overrides.
- **Contracts first**: API/config shapes are defined in
  [`docs/CONTRACTS.md`](./docs/CONTRACTS.md). If a shape needs to change, change
  it there first, then in code and tests.

## Scope

This is a deliberately small project: no cloud, no auth (it's a 127.0.0.1-only
kiosk), no database. New features should fit that local-first model.
