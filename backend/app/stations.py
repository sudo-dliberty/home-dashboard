"""Stations router + registry — bundled NYC subway station data and the
route→realtime-feed map.

Implements ``GET /api/stations`` per the CONTRACTS.md contract:

* ``GET /api/stations?q=<query>&limit=<n>`` — case-insensitive substring search
  on station name (also matches an exact ``stop_id``). Empty/short ``q`` returns
  the first ``limit`` stations.
* ``GET /api/stations/{stop_id}`` — one registry record, or 404
  ``{"error": "unknown_station"}``.

The registry is built from MTA's published *Subway Stations* dataset
(``data.ny.gov`` view ``39hk-dx4f``) and shipped as ``data/stations.json``. Each
record is the parent GTFS stop (no ``N``/``S`` direction suffix) which is exactly
what ``/api/trains`` needs to derive the ``...N`` / ``...S`` stop ids.

It also exposes a static **route → realtime feed URL** map covering every MTA
GTFS-realtime feed group, so ``/api/trains`` can resolve which feed(s) serve a
station's selected routes without hardcoding the single NQRW feed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

# --------------------------------------------------------------------------- #
# Registry loading
# --------------------------------------------------------------------------- #

# Path relative to this module so it resolves regardless of the process cwd.
_DATA_PATH = Path(__file__).parent / "data" / "stations.json"


def _load_registry() -> list[dict[str, Any]]:
    """Read and parse the bundled stations.json (called once at import)."""
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# Module global cache — the JSON is static, load it exactly once at import.
_STATIONS: list[dict[str, Any]] = _load_registry()
# stop_id → record, for O(1) lookups in get_station / direction_labels.
_BY_ID: dict[str, dict[str, Any]] = {s["stop_id"]: s for s in _STATIONS}


# --------------------------------------------------------------------------- #
# Route → realtime feed map
# --------------------------------------------------------------------------- #

# Base reused from config's NQRW URL so the host/path stays in lockstep; the
# suffix after ``gtfs`` is what varies between feed groups (empty for 1-7/S).
_FEED_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"

_FEED_NUMBERED = _FEED_BASE  # 1,2,3,4,5,6,7,S (42 St shuttle) — no suffix
_FEED_ACE = f"{_FEED_BASE}-ace"  # A,C,E + H (Rockaway), FS (Franklin shuttle)
_FEED_BDFM = f"{_FEED_BASE}-bdfm"  # B,D,F,M
_FEED_G = f"{_FEED_BASE}-g"  # G
_FEED_JZ = f"{_FEED_BASE}-jz"  # J,Z
_FEED_NQRW = f"{_FEED_BASE}-nqrw"  # N,Q,R,W
_FEED_L = f"{_FEED_BASE}-l"  # L
_FEED_SI = f"{_FEED_BASE}-si"  # Staten Island Railway

# Individual route code → feed URL. Keys are the codes that appear in the
# registry's ``routes`` (split from "Daytime Routes"), plus a few extra service
# labels (H, FS, SI) for completeness.
ROUTE_FEEDS: dict[str, str] = {
    # Numbered IRT lines + 42 St shuttle share the suffix-less feed.
    "1": _FEED_NUMBERED,
    "2": _FEED_NUMBERED,
    "3": _FEED_NUMBERED,
    "4": _FEED_NUMBERED,
    "5": _FEED_NUMBERED,
    "6": _FEED_NUMBERED,
    "7": _FEED_NUMBERED,
    "S": _FEED_NUMBERED,  # 42 St shuttle (registry collapses all shuttles to "S")
    "GS": _FEED_NUMBERED,  # GTFS route_id for the 42 St shuttle
    # 8th Av lines + Rockaway/Franklin shuttles.
    "A": _FEED_ACE,
    "C": _FEED_ACE,
    "E": _FEED_ACE,
    "H": _FEED_ACE,  # Rockaway Park shuttle
    "FS": _FEED_ACE,  # Franklin Av shuttle
    # 6th Av lines.
    "B": _FEED_BDFM,
    "D": _FEED_BDFM,
    "F": _FEED_BDFM,
    "M": _FEED_BDFM,
    # Crosstown.
    "G": _FEED_G,
    # Nassau St / Jamaica.
    "J": _FEED_JZ,
    "Z": _FEED_JZ,
    # Broadway lines.
    "N": _FEED_NQRW,
    "Q": _FEED_NQRW,
    "R": _FEED_NQRW,
    "W": _FEED_NQRW,
    # 14 St-Canarsie.
    "L": _FEED_L,
    # Staten Island Railway (registry uses "SIR"; "SI" kept as an alias).
    "SIR": _FEED_SI,
    "SI": _FEED_SI,
}


def feed_for_route(route: str) -> str | None:
    """Return the realtime feed URL serving a single route, or None if unknown.

    Lookup is case-sensitive to GTFS conventions but falls back to upper-casing
    so callers can pass lowercase route codes defensively.
    """
    if route in ROUTE_FEEDS:
        return ROUTE_FEEDS[route]
    return ROUTE_FEEDS.get(route.upper())


def feeds_for_routes(routes) -> set[str]:
    """Union of feed URLs needed to cover an iterable of route codes.

    Unknown routes are silently skipped — the caller decides what to do with an
    empty set (e.g. a station whose routes we can't map).
    """
    feeds: set[str] = set()
    for route in routes:
        url = feed_for_route(route)
        if url is not None:
            feeds.add(url)
    return feeds


# --------------------------------------------------------------------------- #
# Registry queries
# --------------------------------------------------------------------------- #

# Below this length a query is treated as "empty" — just return the head of the
# list rather than running a substring match that would match almost everything.
_MIN_QUERY_LEN = 1


def search_stations(q: str, limit: int = 25) -> list[dict[str, Any]]:
    """Case-insensitive substring search on station name.

    An exact ``stop_id`` match is also honoured (and floated to the front) so a
    user who knows the GTFS id can pull up the station directly. Empty/short
    queries return the first ``limit`` registry records.
    """
    if limit < 0:
        limit = 0

    query = (q or "").strip()
    if len(query) < _MIN_QUERY_LEN:
        return _STATIONS[:limit]

    needle = query.lower()

    # Exact stop_id hit ranks first; it's the most specific possible match.
    exact = _BY_ID.get(query) or _BY_ID.get(query.upper())

    results: list[dict[str, Any]] = []
    if exact is not None:
        results.append(exact)
    for station in _STATIONS:
        if station is exact:
            continue
        if needle in station["name"].lower():
            results.append(station)

    return results[:limit]


def get_station(stop_id: str) -> dict[str, Any] | None:
    """Return the registry record for a parent GTFS stop id, or None."""
    return _BY_ID.get(stop_id)


def direction_labels(stop_id: str) -> tuple[str | None, str | None]:
    """Return ``(north_label, south_label)`` for a station, or ``(None, None)``.

    Used by ``/api/trains`` to label the two platform directions from the
    registry instead of hardcoding "Manhattan"/"Queens".
    """
    station = _BY_ID.get(stop_id)
    if station is None:
        return (None, None)
    return (station.get("north_label"), station.get("south_label"))


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #

router = APIRouter(prefix="/api", tags=["stations"])


@router.get("/stations")
async def list_stations(q: str = "", limit: int = 25) -> Any:
    """Search the station registry by name (or exact stop_id)."""
    return search_stations(q, limit)


@router.get("/stations/{stop_id}")
async def get_station_route(stop_id: str) -> Any:
    """Return a single station record, or 404 if the stop id is unknown."""
    station = get_station(stop_id)
    if station is None:
        return JSONResponse(
            status_code=404, content={"error": "unknown_station"}
        )
    return station
