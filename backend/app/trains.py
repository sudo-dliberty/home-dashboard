"""Trains router — generalized MTA GTFS-realtime arrival board.

Implements ``GET /api/trains`` per docs/CONTRACTS.md (the generalized shape).

The endpoint is driven by **runtime config** (``config_store.get_runtime_config``),
not the frozen ``Settings`` singleton:

* ``trains.station_stop_id`` — the parent GTFS stop (e.g. ``R06`` for 36 Av).
* ``trains.routes`` — the subset of routes to show at that station.

The selected routes may span multiple MTA realtime feeds, so:

* ``stations.feeds_for_routes(routes)`` resolves the set of feed URLs to fetch.
* Each feed is fetched concurrently and cached **per feed URL** for
  ``train_feed_cache_seconds`` (infra-only, stays on ``Settings``).
* On a feed's upstream failure we fall back to that feed's cached bytes marked
  stale; the overall response is ``stale`` if *any* contributing feed is stale.
* If no feed can be fetched and none is cached → HTTP 503.

Parsing generalizes the old Queens/Manhattan suffix logic to north/south:
``{station_stop_id}N`` → north bucket, ``{station_stop_id}S`` → south bucket.
Arrivals from every fetched feed are merged into those two buckets, keeping only
the selected routes, dropping arrivals <1 or >``train_max_minutes`` away, and
sorting ascending by minutes. Direction labels come from the station registry.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from google.transit import gtfs_realtime_pb2

from . import config_store, stations
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trains"])

# Per-feed cache: feed URL → {"feed_bytes": bytes, "fetched_at_unix": int}. We
# keep the raw protobuf so "minutes" can be recomputed on cache hits, and the
# fetch time so the overall response can report feed age / TTL. Guarded by a
# single asyncio.Lock — fetches are concurrent but cache mutation is serialized.
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = asyncio.Lock()

_NORTH_STOP_SUFFIX = "N"  # {parent}N — north platform
_SOUTH_STOP_SUFFIX = "S"  # {parent}S — south platform

# Fallback direction labels for stations missing from the registry.
_FALLBACK_NORTH_LABEL = "Northbound"
_FALLBACK_SOUTH_LABEL = "Southbound"


def _utc_now() -> datetime:
    """Indirection so tests can monkeypatch this single function."""
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    """ISO 8601 in UTC with a trailing ``Z`` (not ``+00:00``)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_into_buckets(
    feed_bytes: bytes,
    *,
    station_stop_id: str,
    routes: set[str],
    now: datetime,
    north: list[dict[str, Any]],
    south: list[dict[str, Any]],
) -> None:
    """Parse one GTFS-realtime feed and append matching arrivals into the
    shared ``north`` / ``south`` buckets.

    Buckets are passed in (not returned) so arrivals from multiple feeds serving
    the same station merge naturally before the caller sorts.

    Parameters
    ----------
    feed_bytes:
        Raw protobuf bytes as served by an MTA endpoint.
    station_stop_id:
        Parent GTFS stop id; ``{id}N`` / ``{id}S`` select the two platforms.
    routes:
        Only arrivals whose ``route_id`` is in this set are kept.
    now:
        Reference timestamp used to compute ``minutes`` and to drop entries that
        are in the past or beyond ``train_max_minutes``. Injectable for tests.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_unix = int(now.timestamp())

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)

    north_stop_id = f"{station_stop_id}{_NORTH_STOP_SUFFIX}"
    south_stop_id = f"{station_stop_id}{_SOUTH_STOP_SUFFIX}"
    max_minutes = settings.train_max_minutes

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        route_id = tu.trip.route_id
        if route_id not in routes:
            continue

        for stu in tu.stop_time_update:
            stop_id = stu.stop_id
            if stop_id == north_stop_id:
                bucket = north
            elif stop_id == south_stop_id:
                bucket = south
            else:
                continue

            # Prefer arrival.time; fall back to departure.time (terminal trips
            # can omit arrival — cheap defensive coding).
            arr_time = 0
            if stu.HasField("arrival") and stu.arrival.time:
                arr_time = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time:
                arr_time = stu.departure.time
            if arr_time <= 0:
                continue

            seconds_until = arr_time - now_unix
            minutes = round(seconds_until / 60)
            if minutes < 1 or minutes > max_minutes:
                continue

            arrival_dt = datetime.fromtimestamp(arr_time, tz=timezone.utc)
            bucket.append(
                {
                    "route": route_id,
                    "minutes": minutes,
                    "arrival": _iso_z(arrival_dt),
                }
            )


def parse_feeds(
    feeds: list[bytes],
    *,
    station_stop_id: str,
    routes: set[str],
    now: datetime,
) -> dict[str, list[dict[str, Any]]]:
    """Parse and merge one or more feeds into sorted north/south arrival lists.

    A station served by multiple feeds (rare, but possible) has each feed's
    arrivals merged into the same buckets before sorting ascending by minutes.
    """
    north: list[dict[str, Any]] = []
    south: list[dict[str, Any]] = []
    for feed_bytes in feeds:
        _parse_into_buckets(
            feed_bytes,
            station_stop_id=station_stop_id,
            routes=routes,
            now=now,
            north=north,
            south=south,
        )
    north.sort(key=lambda r: r["minutes"])
    south.sort(key=lambda r: r["minutes"])
    return {"north": north, "south": south}


async def _fetch_feed(url: str) -> bytes:
    """GET a single live feed. Raises on any non-2xx or network error."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _render(
    feeds: list[bytes],
    *,
    station_stop_id: str,
    routes: set[str],
    newest_fetched_at_unix: int,
    now: datetime,
    stale: bool,
) -> dict[str, Any]:
    """Build the full API response dict from the contributing feeds' bytes.

    ``fetched_at`` / ``feed_age_s`` are reported against the **newest**
    contributing feed fetch, so the age reflects the freshest data on screen.
    """
    parsed = parse_feeds(
        feeds, station_stop_id=station_stop_id, routes=routes, now=now
    )

    station = stations.get_station(station_stop_id)
    name = station["name"] if station else station_stop_id
    north_label, south_label = stations.direction_labels(station_stop_id)

    return {
        "station": name,
        "stop_id": station_stop_id,
        "fetched_at": _iso_z(
            datetime.fromtimestamp(newest_fetched_at_unix, tz=timezone.utc)
        ),
        "feed_age_s": max(0, int(now.timestamp()) - newest_fetched_at_unix),
        "stale": stale,
        "north": {
            "label": north_label or _FALLBACK_NORTH_LABEL,
            "arrivals": parsed["north"],
        },
        "south": {
            "label": south_label or _FALLBACK_SOUTH_LABEL,
            "arrivals": parsed["south"],
        },
    }


async def _get_feed_bytes(
    url: str, *, now_unix: int
) -> tuple[bytes | None, int | None, bool]:
    """Resolve one feed's bytes: ``(feed_bytes, fetched_at_unix, stale)``.

    Cache-hit-within-TTL → cached bytes, not stale. Otherwise refresh; on
    failure fall back to cached bytes marked stale, or ``(None, None, False)``
    if nothing is available. Mutates the per-URL cache on a successful refresh.
    """
    entry = _cache.get(url)
    cached_bytes = entry["feed_bytes"] if entry else None
    cached_at = entry["fetched_at_unix"] if entry else None

    # Serve from cache if still within TTL.
    if (
        cached_bytes is not None
        and cached_at is not None
        and (now_unix - cached_at) < settings.train_feed_cache_seconds
    ):
        return cached_bytes, cached_at, False

    # Otherwise try to refresh this feed.
    try:
        fresh = await _fetch_feed(url)
    except Exception as exc:  # noqa: BLE001 — upstream can fail in many ways
        logger.warning("MTA feed fetch failed for %s: %s", url, exc)
        if cached_bytes is not None and cached_at is not None:
            return cached_bytes, cached_at, True
        return None, None, False

    _cache[url] = {"feed_bytes": fresh, "fetched_at_unix": now_unix}
    return fresh, now_unix, False


@router.get("/trains")
async def get_trains() -> Any:
    now = _utc_now()
    now_unix = int(now.timestamp())

    cfg = config_store.get_runtime_config()
    station_stop_id = cfg["trains"]["station_stop_id"]
    routes = set(cfg["trains"]["routes"])

    feed_urls = sorted(stations.feeds_for_routes(routes))

    async with _cache_lock:
        # No feed maps to the selected routes — nothing fetchable, return an
        # empty (but well-formed) board rather than erroring.
        if not feed_urls:
            return _render(
                [],
                station_stop_id=station_stop_id,
                routes=routes,
                newest_fetched_at_unix=now_unix,
                now=now,
                stale=False,
            )

        # Fetch (or cache-resolve) every feed concurrently for latency.
        results = await asyncio.gather(
            *(_get_feed_bytes(url, now_unix=now_unix) for url in feed_urls)
        )

        contributing: list[bytes] = []
        newest_fetched_at: int | None = None
        any_stale = False
        for feed_bytes, fetched_at, stale in results:
            if feed_bytes is None or fetched_at is None:
                continue
            contributing.append(feed_bytes)
            any_stale = any_stale or stale
            if newest_fetched_at is None or fetched_at > newest_fetched_at:
                newest_fetched_at = fetched_at

        # No feed could be fetched and none cached → 503.
        if not contributing or newest_fetched_at is None:
            return JSONResponse(
                status_code=503, content={"error": "feed_unavailable"}
            )

        return _render(
            contributing,
            station_stop_id=station_stop_id,
            routes=routes,
            newest_fetched_at_unix=newest_fetched_at,
            now=now,
            stale=any_stale,
        )


def _reset_cache_for_tests() -> None:
    """Test helper — clear the per-feed cache between tests."""
    _cache.clear()
