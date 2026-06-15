# AGENTS.md

Map of the repo for humans and AI coding agents (Claude Code, Cursor, etc.).
For the user-facing feature tour see [`README.md`](./README.md); for design
rationale see [`PLAN.md`](./PLAN.md); for exact API/config shapes see the source
of truth, [`docs/CONTRACTS.md`](./docs/CONTRACTS.md).

## What this is

A local-only "before you leave the house" dashboard for a Raspberry Pi driving a
monitor in Chromium kiosk mode: next trains at a configurable NYC subway
station, local weather, the time, and a rotating photo slideshow. No cloud, no
auth (it binds to 127.0.0.1), no database. A single Uvicorn process serves both
the API and the built SPA.

## Directory layout

```
home-dashboard/
├── backend/                 FastAPI app + tests
│   └── app/
│       ├── main.py          app, router wiring, /api/health, static SPA mount
│       ├── config.py        pydantic-settings Settings (seed defaults + infra)
│       ├── config_store.py  layered runtime config (defaults ⊕ settings.json)
│       ├── settings_api.py  GET/PUT /api/settings
│       ├── stations.py      station registry + route→feed map, GET /api/stations
│       ├── trains.py        generalized GTFS-realtime board, GET /api/trains
│       ├── weather.py       NWS primary + Open-Meteo fallback, GET /api/weather
│       ├── photos.py        list/serve images, GET /api/photos[/{file}]
│       ├── cache.py         simple TTL cache helper
│       └── data/stations.json   bundled MTA station registry
├── frontend/                React + TS + Vite + Tailwind SPA
│   └── src/
│       ├── App.tsx          4-panel grid; hash route to settings; gear
│       ├── api.ts           typed fetchers (mirror docs/CONTRACTS.md)
│       ├── components/      RouteBullet, SettingsGear
│       ├── panels/          Trains, Clock, Weather, Photos
│       └── settings/        SettingsContext, SettingsScreen
├── scripts/                 dev-mac.sh, build.sh, kiosk-launch.sh, pi/*
└── docs/                    CONTRACTS.md, screenshots
```

## Configuration model (important)

Config is **layered** — get this right before touching config code:

- **Seed defaults** come from `.env` via `pydantic-settings`
  (`app/config.py` `Settings`). These include **infra-only** keys that are NOT
  user-editable: `host`, `port`, `static_dir`, `*_cache_seconds`,
  `mta_*_feed_url`.
- **Runtime overrides** live in a gitignored **`settings.json`** at the repo
  root, written by the settings UI. Read live (cached by mtime), written
  atomically.
- **Effective config** = defaults deep-merged with overrides. Always read
  user-tunable fields through `config_store.get_runtime_config()`, never the
  frozen `Settings` singleton.
- **User-tunable** (UI → `settings.json`): `time.{timezone,clock_24h}`,
  `weather.{lat,lon,label,user_agent}`, `photos.directory`,
  `trains.{station_stop_id,routes}`.

## API endpoints

Full schemas in [`docs/CONTRACTS.md`](./docs/CONTRACTS.md). Summary:

- `GET /api/health` — `{ ok, uptime_s, station_stop_id }`
- `GET /api/settings` / `PUT /api/settings` — read/write effective config
- `GET /api/stations?q=` / `GET /api/stations/{stop_id}` — station registry
- `GET /api/trains` — generalized north/south arrival board (multi-feed)
- `GET /api/weather` — current + 12 hourly + summary
- `GET /api/photos` / `GET /api/photos/{filename}` — list + stream images

## Run / test / build

```sh
# Dev (backend :8000 + Vite :5173)
./scripts/dev-mac.sh

# Backend tests
cd backend && .venv/bin/python -m pytest tests/ -q

# Frontend build (must stay clean)
cd frontend && npm run build
```

## Conventions

- **Contracts first.** Change `docs/CONTRACTS.md` before changing a shape.
- Backend: async upstream calls, per-feed/per-source caching, stale-on-failure
  with last-good data, 503 only when there's no cache at all.
- Frontend: no router lib; settings reached via `#/settings` hash route. Keep
  fetchers and types in `api.ts`.
- Tests live in `backend/tests/`; they monkeypatch `Settings` attributes and
  `config_store.SETTINGS_PATH`. Don't snapshot `Settings` at import time.
- Local-first scope: no cloud, no auth, no DB.
