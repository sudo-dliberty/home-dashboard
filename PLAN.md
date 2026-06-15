# Astoria Home Dashboard — Plan

> Local-only "before you leave the house" dashboard for a Raspberry Pi driving a
> 27" LG monitor in fullscreen Chrome kiosk. No cloud. ZIP 11106, 36 Av (N/W)
> Astoria. All work merges to `main`.

---

## 1. Verified facts (real data, not guesses)

| Item | Value | How verified |
|---|---|---|
| MTA NQRW GTFS-realtime feed URL | `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw` | `curl -L` → HTTP 200, 82 KB protobuf body. No API key, no `User-Agent` needed. (HEAD is blocked → use GET only.) |
| MTA static GTFS bundle | `https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip` | Downloaded ~5.6 MB zip (`stops.txt`, `routes.txt`, etc.). |
| **36 Av Astoria parent stop_id** | **`R06`** | `stops.txt` row: `R06,36 Av,40.756804,-73.929575,1,` |
| Queens-bound (toward Astoria-Ditmars) | **`R06N`** | `R06N,36 Av,…,,R06` — `N` suffix = uptown/Queens for the Astoria branch. |
| Manhattan-bound | **`R06S`** | `R06S,36 Av,…,,R06`. |
| Adjacent stops (sanity check on direction) | `R01` Astoria-Ditmars Blvd (terminal, N of R06), `R03` Astoria Blvd (between R06 and R01) | `stops.txt`. |
| NQRW route color | **`#F6BC26`** on `#000000` text | `routes.txt` — official BMT Broadway yellow for N, Q, R, W. |
| N service span | All times, Astoria-Ditmars ↔ Coney Island | `routes.txt` long description. |
| W service span | **Weekdays only**, Astoria-Ditmars ↔ Whitehall St | `routes.txt` long description. (Dashboard must not show "no W trains" as an error on weekends/late nights.) |
| Weather: NWS works for our coords | `GET https://api.weather.gov/points/40.7568,-73.9296` → 200 JSON | Curl. Requires `User-Agent` header (NWS policy). No key. |
| Weather: Open-Meteo works as fallback | `GET https://api.open-meteo.com/v1/forecast?…` → 200 JSON | Curl. No header, no key. |

> The `mimouncadosch/MTA-API` reference repo is **scheduled-only** (Python 2,
> Flask 0.10, reads `stop_times.txt`). It is useful as a stop_id discovery
> pattern but **not** for realtime — we go straight to GTFS-rt protobuf.

Outstanding verification deferred to install/run time:
- **Actual monitor resolution.** Layout is built in `vw`/`vh` + CSS grid so it
  adapts; the 1920×1080 number is treated as a likely-but-unconfirmed default.
  Read the real resolution on the Pi during Phase 6.
- **Photo directory path.** User-supplied; expressed via env var.

---

## 2. Tech choices (with rationale)

**Backend: Python 3.11+ with FastAPI + Uvicorn.**
Why: protobuf parsing is best-supported in Python via the official
`gtfs-realtime-bindings` package; HEIC handling (`pillow-heif`) is trivial in
Python; FastAPI is async-friendly for parallel upstream polling and runs cleanly
on a Pi via a single Uvicorn process; one language for all three data services
keeps deployment simple.

**Frontend: React + TypeScript + Vite + Tailwind CSS.**
Why: Vite gives fast dev iteration on the Mac; TS keeps the small API contract
honest; Tailwind lets us hit a kiosk-legible dark theme without a CSS framework.
No router needed (single page).

**Serving in production:** the FastAPI app mounts the built frontend (`/`) as
static files. **Single port, single process** → simplest possible Pi systemd
unit, no CORS, no nginx.

**Time:** rendered client-side with `Intl.DateTimeFormat` in
`America/New_York`. Backend stays UTC.

**Polling intervals:** trains 30 s, weather 60 s, photos rotate every 60 s,
clock client tick every 1 s. Each panel keeps showing last-known data on fetch
failure with a small "stale Xm ago" badge.

---

## 3. Repo layout

```
home-dashboard/
├── PLAN.md                      ← this file
├── README.md                    ← Mac + Pi run instructions (Phase 6)
├── .gitignore
├── .env.example                 ← PHOTO_DIR, WEATHER_PROVIDER, etc.
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              ← FastAPI app, static mount, /health
│   │   ├── config.py            ← env-driven settings (pydantic-settings)
│   │   ├── trains.py            ← GTFS-rt fetch + parse for R06
│   │   ├── weather.py           ← NWS primary, Open-Meteo fallback
│   │   ├── photos.py            ← list + serve from PHOTO_DIR
│   │   └── cache.py             ← simple TTL cache for upstream calls
│   └── tests/
│       ├── fixtures/
│       │   └── nqrw_sample.pb   ← captured live feed snapshot
│       ├── test_trains.py
│       ├── test_weather.py
│       └── test_photos.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── tailwind.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx              ← 4-panel CSS grid
│       ├── api.ts               ← typed fetchers
│       ├── components/
│       │   └── RouteBullet.tsx  ← yellow circle w/ letter (Reddit visual)
│       └── panels/
│           ├── Trains.tsx
│           ├── Clock.tsx
│           ├── Weather.tsx
│           └── Photos.tsx
└── scripts/
    ├── dev-mac.sh               ← runs backend + Vite dev server
    ├── build.sh                 ← builds frontend → backend/static/
    ├── kiosk-launch.sh          ← Chrome --kiosk on Mac (for dry-run)
    └── pi/
        ├── home-dashboard.service       ← systemd unit
        ├── kiosk.desktop                ← LXDE autostart entry
        └── install.sh                   ← idempotent Pi setup
```

---

## 4. API contracts

> **Note:** the shapes below are the *original* Phase 0–5 contracts. The trains
> endpoint was later generalized (north/south, multi-feed) and `/api/settings`
> + `/api/stations` were added. The current source of truth for all API/config
> shapes is [`docs/CONTRACTS.md`](./docs/CONTRACTS.md); see §10 for the summary.

### `GET /api/health`
```json
{ "ok": true, "uptime_s": 12345 }
```

### `GET /api/trains`
```json
{
  "station": "36 Av",
  "stop_id": "R06",
  "fetched_at": "2026-05-31T18:42:11Z",
  "feed_age_s": 7,
  "queens_bound": [
    { "route": "N", "minutes": 3, "arrival": "2026-05-31T18:45:00Z" },
    { "route": "W", "minutes": 9, "arrival": "2026-05-31T18:51:00Z" }
  ],
  "manhattan_bound": [
    { "route": "N", "minutes": 2, "arrival": "2026-05-31T18:44:30Z" }
  ]
}
```
Backend rules:
- Only routes `N` and `W` are included.
- Arrivals in the past or > 30 min in the future are dropped.
- Sorted ascending by minutes.
- `minutes` is `round(seconds_until / 60)`; values < 1 render as "Now" on the
  client.
- Backend caches the parsed feed for 15 s to absorb bursty client polling.
- On upstream failure: return last good data with HTTP 200 and a
  `"stale": true` flag; only return 5xx if there is no cached data at all.

### `GET /api/weather`
```json
{
  "fetched_at": "2026-05-31T18:42:11Z",
  "provider": "nws",
  "current": {
    "temp_f": 71,
    "feels_like_f": 70,
    "condition": "Partly Cloudy",
    "icon": "few-clouds-day",
    "precip_prob": 10
  },
  "hourly": [
    { "time": "2026-05-31T19:00:00-04:00", "temp_f": 70, "precip_prob": 15, "condition": "Partly Cloudy" },
    ...12 entries...
  ],
  "summary": {
    "needs_coat": false,
    "needs_umbrella": false,
    "min_temp_next_12h_f": 62,
    "max_precip_prob_next_12h": 20
  }
}
```
Rules: NWS is primary. If NWS fails or returns no usable forecast, fall back to
Open-Meteo. `needs_coat = min_temp < 55`. `needs_umbrella = max_precip_prob >= 40`.

### `GET /api/photos`
```json
{ "photos": ["IMG_0001.jpg", "vacation.png", ...] }
```

### `GET /api/photos/{filename}`
Streams the file from `PHOTO_DIR`. Path traversal blocked
(`Path(filename).name == filename` check). Accepts `.jpg`, `.jpeg`, `.png`,
`.webp`, `.gif`. HEIC support is documented but off by default; toggled by
installing `pillow-heif` and setting `PHOTO_HEIC=1`.

---

## 5. Frontend layout

A 12-column CSS grid filling the viewport. Default at 16:9:

```
┌──────────────────────────────────┬──────────────────┐
│                                  │     CLOCK        │  (top-right, big)
│            PHOTOS                ├──────────────────┤
│        (rotates every 60s)       │    WEATHER       │  (current + hourly strip)
│                                  ├──────────────────┤
│                                  │     TRAINS       │  (yellow N / W bullets)
└──────────────────────────────────┴──────────────────┘
```

- **`RouteBullet`** component: a 1em-diameter circle, fill `#F6BC26`, text
  `#000000`, weight 900, sans-serif, contains the letter `N` or `W`. Matches the
  Reddit reference visual: bullet + minutes ("N  3 min").
- Trains panel: two stacked sections — "→ Manhattan" and "→ Queens (Astoria)".
  Each row: `<RouteBullet>` + minutes (big) + scheduled time (small).
- Weather panel: large temp + condition icon + "coat?" / "umbrella?" chips +
  12-hour scrolling strip below.
- Photo panel: `object-fit: contain`, centered on a black background, crossfade
  between rotations.
- Clock: NY time, `HH:MM` huge, weekday + date below.
- Each panel shows a small stale-data badge if its last successful fetch is
  older than 3× its poll interval.

---

## 6. Build phases (each ends with commit + push to `main`)

| Phase | Deliverable | Parallelizable? |
|---|---|---|
| 0 | `PLAN.md`, `.gitignore`, repo layout dirs created | — |
| 1 | Backend scaffold: `main.py`, `config.py`, `/api/health`, project bootstrap, `requirements.txt` | — |
| 2 | `/api/trains` with live `R06N`/`R06S` parsing + mocked-feed test | Could parallel with 3 & 4 |
| 3 | `/api/weather` (NWS + OM fallback) + test | Could parallel with 2 & 4 |
| 4 | `/api/photos` list + static serve + path-traversal test | Could parallel with 2 & 3 |
| 5 | React frontend: all 4 panels, polling, stale states, dark theme | The 4 panels can be built by parallel subagents in worktrees |
| 6 | Mac end-to-end kiosk dry-run, Pi systemd unit, autostart docs, `README.md` | — |

**Worktree policy for any parallel subagent work:**
- Each subagent is given a worktree under `.worktrees/<branch-name>/` and a
  branch `phaseN-<slug>`.
- Subagent acceptance includes: tests pass locally, no lint errors, clean
  `git status` in the worktree.
- Before completing, subagent does: commit → fetch origin → rebase onto
  `origin/main` → resolve conflicts → fast-forward merge to `main` → push
  `main` → delete the worktree directory → delete the branch.
- The orchestrator (me) verifies `main` has the expected changes and that no
  worktrees or feature branches remain.

---

## 7. Deployment (Phase 6)

**Mac dev:**
```
./scripts/dev-mac.sh      # uvicorn :8000 + vite :5173 (proxy /api → :8000)
```

**Pi production (single process):**
1. `./scripts/build.sh` — `npm run build` → static files into
   `backend/app/static/`.
2. `backend/` installed as a venv; FastAPI serves both `/api/*` and the
   built SPA.
3. `scripts/pi/home-dashboard.service` — systemd unit running
   `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. `scripts/pi/kiosk.desktop` — LXDE autostart entry that launches
   `chromium-browser --kiosk --noerrdialogs --disable-infobars
   --disable-pinch --overscroll-history-navigation=0
   --check-for-update-interval=31536000 http://localhost:8000`.
5. `scripts/pi/install.sh` — idempotent installer: apt deps, venv, npm build,
   systemd enable, autostart copy. Documents how to verify the live
   resolution with `xrandr` and update CSS variables if non-1920×1080.

---

## 8. Risks & known unknowns

- **MTA feed shape changes** — unlikely, but `gtfs-realtime-bindings` is the
  canonical parser; we test against a captured fixture.
- **NWS rate-limit / outage** — Open-Meteo fallback covers it.
- **HEIC photos** — handled as documented opt-in; default skips them.
- **Monitor resolution differs from 1920×1080** — layout uses relative units;
  the install doc has a verification step.
- **Pi clock drift** — relies on systemd-timesyncd; not in scope to manage.
- **Power/network loss** — out of scope; Chrome reconnects, panels show stale.

---

## 9. What I will NOT build

- Any cloud component (no AWS, no hosted DB, no remote logging).
- Authentication — it's a LAN-only kiosk on the user's own network.
- Service alerts/disruptions panel (not requested; keep panels focused).

> **Updated:** two original non-goals were since built — see §10. A **settings
> UI** now exists (the env-var-only stance relaxed to a *layered* model: `.env`
> seeds + `settings.json` overrides), and **multi-station / any-line** support
> replaced the 36 Av-only scope. Auth and cloud remain out of scope.

---

## 10. Settings + generalized trains (as implemented)

The dashboard outgrew its Astoria-only origins. This section documents the
shipped state; the **API/config source of truth** is
[`docs/CONTRACTS.md`](./docs/CONTRACTS.md) — prefer it over §4 where they differ.

**Layered configuration.** `.env` (via `pydantic-settings`, `app/config.py`)
provides *seed defaults* plus infra-only keys (host, port, cache TTLs,
static_dir, feed URLs). Runtime overrides live in a gitignored **`settings.json`**
at the repo root, written by the settings UI. The *effective config* =
defaults deep-merged with overrides, exposed by `app/config_store.py`
(`get_runtime_config()` / `update_runtime_config()`): read live but cached by
file mtime, written atomically (temp file + `os.replace`). User-tunable fields
are always read through the store, never the frozen `Settings` singleton.

**Station registry.** `app/stations.py` loads a bundled
`app/data/stations.json` (built from MTA's published Subway Stations dataset:
GTFS stop id, name, borough, daytime routes, North/South direction labels) and
serves `GET /api/stations?q=` + `GET /api/stations/{stop_id}`. A static
**route → realtime feed-URL** map covers every MTA GTFS-rt feed group
(1-7/S, A-C-E, B-D-F-M, G, J-Z, L, N-Q-R-W, SIR).

**Generalized trains.** `GET /api/trains` is now driven by runtime config
(`trains.station_stop_id` + `trains.routes`). It resolves the feed(s) serving
the selected routes, fetches their union concurrently (per-feed cache),
parses arrivals into **north/south** buckets (`{stop_id}N` / `{stop_id}S`),
keeps only the selected routes, and labels the two directions from the
registry. Stale-on-failure and 503-when-no-cache semantics are preserved, now
per-feed (response is `stale` if any contributing feed is stale).

**Settings API + UI.** `app/settings_api.py` exposes `GET`/`PUT /api/settings`
(no auth — 127.0.0.1-only; invalid input → 422 per-field). The frontend adds a
hash-routed `SettingsScreen` (`frontend/src/settings/`) reachable via a
hover-to-reveal `SettingsGear`, with sections for Time, Weather, Photos, and a
search-any-station / pick-lines Subway picker. Changes apply live without a
restart.

---

**Confirm this plan and I'll start Phase 1.**
