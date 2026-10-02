# API & Config Contracts (settings feature)

> **Single source of truth** for the settings work. Every backend/frontend
> subagent must conform to the shapes below. If a shape needs to change,
> change it *here first*, then in code.

## Layered configuration

- **Seed defaults** come from `.env` via `pydantic-settings` (existing
  `app/config.py` `Settings` singleton). These are infrastructure + initial
  values.
- **Runtime overrides** live in a gitignored **`settings.json`** at the repo
  root, written by the settings UI. Read **live per request** (cache by file
  mtime), written **atomically** (temp file + `os.replace`).
- The **effective config** = defaults deep-merged with overrides. User-tunable
  fields are read through `config_store.get_runtime_config()`, never the frozen
  `Settings` singleton.
- Infra-only fields stay on `.env`/`Settings` and are NOT user-editable:
  `host`, `port`, `static_dir`, `*_cache_seconds`, `train_feed_cache_seconds`,
  `mta_*_feed_url` overrides.

`settings.json` must be added to `.gitignore`.

## Effective config / `settings.json` shape

```jsonc
{
  "time":    { "timezone": "America/New_York", "clock_24h": false },
  "weather": { "lat": 40.7568, "lon": -73.9296,
               "label": "Astoria 11106",
               "zip": "11106",
               "user_agent": "home-dashboard (local, you@example.com)" },
  "photos":  { "directory": "/absolute/path/to/pictures" },
  "trains":  { "station_stop_id": "R06", "routes": ["N", "W"] }
}
```

- `time.timezone`: IANA tz name (validate against `zoneinfo.available_timezones()`).
- `weather.lat`/`lon` are the source of truth the backend fetches with.
  `weather.zip` is optional and for display/convenience only — the settings UI
  resolves a ZIP to lat/lon via `GET /api/geocode` and stores all three.
- `trains.routes`: subset of the routes the selected station actually serves.

## `GET /api/geocode?zip=<US ZIP>`
Resolves a 5-digit US ZIP to coordinates via the key-less Zippopotam.us service.
Returns `{ "zip", "lat", "lon", "label" }` (label like `"Astoria, NY"`).
Malformed ZIP → `400 {"error":"invalid_zip"}`; unknown/lookup failure →
`404 {"error":"zip_not_found"}`. Used only by the settings UI.

## `GET /api/settings`
Returns the **effective** config (defaults + overrides), exactly the shape above.

## `PUT /api/settings`
Accepts a full or partial config object (same shape, any subset of sections).
Validates, persists the merged overrides to `settings.json`, returns the new
effective config. Invalid input → `422` with per-field messages. No auth
(documented as 127.0.0.1-only).

## `GET /api/stations?q=<query>`
Searches the bundled station registry by name (case-insensitive substring).
Returns up to 25:

```jsonc
[
  { "stop_id": "R06", "name": "36 Av", "borough": "Q",
    "routes": ["N", "W"],
    "north_label": "Astoria - Ditmars Blvd", "south_label": "Manhattan" }
]
```

Empty/short `q` → first N stations or `[]` (implementer's choice, documented).
Optionally also `GET /api/stations/{stop_id}` returning one record (404 if
unknown).

## `GET /api/trains` (generalized — REPLACES the Astoria-specific shape)
Driven by `trains.station_stop_id` + `trains.routes` from runtime config. The
backend resolves which MTA feed(s) serve the selected routes (route→feed map),
fetches the union, parses, and labels the two directions from the registry.

```jsonc
{
  "station": "36 Av",
  "stop_id": "R06",
  "fetched_at": "2026-06-14T12:00:00Z",
  "feed_age_s": 12,
  "stale": false,
  "north": { "label": "Astoria - Ditmars Blvd",
             "arrivals": [ { "route": "N", "minutes": 4,
                             "arrival": "2026-06-14T12:04:00Z" } ] },
  "south": { "label": "Manhattan", "arrivals": [ /* ... */ ] }
}
```

- `north` = GTFS `...N` stop suffix, `south` = `...S`. Labels come from the
  registry's `north_label` / `south_label`.
- Caching, stale-on-failure, and 503-when-no-cache semantics are preserved from
  the current implementation, but cache keys are now per-feed.
- Frontend `Trains.tsx` and `api.ts` consume `north`/`south` + their labels
  (no more hardcoded "Manhattan"/"Queens").

## `GET /api/photos/{filename}?max=<px>`
Streams one photo from the configured directory. Optional `max` (integer ≥ 1)
asks for a copy whose long edge is at most that many pixels; it's clamped to
64–3840 and rounded **up** to a multiple of 64. Without `max` the cap is 1920.

- Photos already within the cap are streamed **unchanged** (original type).
- Larger photos are returned as `image/jpeg`: EXIF orientation applied,
  converted to **sRGB** (e.g. from Display P3), Lanczos-resampled, quality 90.
- Resized copies are cached on disk under `$XDG_CACHE_HOME/home-dashboard/photos`
  (default `~/.cache/…`), pruned oldest-first beyond 512 MB.
- `400` bad filename, `404` missing, `415` unsupported extension.

## Station registry data
`backend/app/data/stations.json` — built from MTA's published **Stations.csv**
(columns include GTFS Stop ID, Stop Name, Borough, Daytime Routes, North/South
Direction Labels). Plus a static **route → feed-URL** map in code covering the
MTA realtime feed groups (1-7/S, A-C-E, B-D-F-M, G, J-Z, L, N-Q-R-W, SIR).
