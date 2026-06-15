"""Tests for the station registry, the route→feed map, and /api/stations.

These deliberately avoid importing ``app.main`` (which wires in sibling routers
that may be built by other agents). The registry/feed functions are tested
directly, and the HTTP routes are exercised against a standalone FastAPI app
that only mounts the stations router.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import stations
from app.stations import (
    direction_labels,
    feed_for_route,
    feeds_for_routes,
    get_station,
    router,
    search_stations,
)

# Canonical feed URLs we assert against (mirrors config.py's NQRW value).
_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
_NQRW = f"{_BASE}-nqrw"
_NUMBERED = _BASE  # 1-7 / S share the suffix-less feed


# Standalone app — no dependency on app.main or sibling routers.
def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Registry loading
# --------------------------------------------------------------------------- #

def test_registry_loaded_and_nonempty():
    assert len(stations._STATIONS) > 400  # MTA publishes ~470 stations


def test_known_station_present():
    r06 = get_station("R06")
    assert r06 is not None
    assert r06["name"] == "36 Av"
    assert "N" in r06["routes"]
    assert "W" in r06["routes"]


def test_get_station_unknown_returns_none():
    assert get_station("ZZZ999") is None


# --------------------------------------------------------------------------- #
# search_stations
# --------------------------------------------------------------------------- #

def test_search_by_name_substring():
    results = search_stations("36 Av")
    assert any(s["stop_id"] == "R06" for s in results)


def test_search_is_case_insensitive():
    lower = search_stations("times sq")
    upper = search_stations("TIMES SQ")
    assert lower == upper
    assert len(lower) > 0


def test_search_by_exact_stop_id():
    results = search_stations("R06")
    assert results
    assert results[0]["stop_id"] == "R06"  # exact id floats to the front


def test_search_limit_respected():
    results = search_stations("", limit=5)
    assert len(results) == 5


def test_empty_query_returns_head():
    results = search_stations("")
    assert len(results) == 25  # default limit


# --------------------------------------------------------------------------- #
# Route → feed map
# --------------------------------------------------------------------------- #

def test_feed_for_route_nqrw():
    assert feed_for_route("N") == _NQRW
    assert feed_for_route("W") == _NQRW


def test_feed_for_route_numbered_no_suffix():
    assert feed_for_route("6") == _NUMBERED


def test_feed_for_route_unknown():
    assert feed_for_route("X") is None


def test_feeds_for_routes_nw_union():
    assert feeds_for_routes(["N", "W"]) == {_NQRW}


def test_feeds_for_routes_mixed_union():
    # N/W → nqrw, 6 → numbered: two distinct feeds.
    assert feeds_for_routes(["N", "W", "6"]) == {_NQRW, _NUMBERED}


# --------------------------------------------------------------------------- #
# direction_labels
# --------------------------------------------------------------------------- #

def test_direction_labels_known():
    north, south = direction_labels("R06")
    assert north is not None and south is not None


def test_direction_labels_unknown():
    assert direction_labels("ZZZ999") == (None, None)


# --------------------------------------------------------------------------- #
# HTTP routes
# --------------------------------------------------------------------------- #

def test_http_search():
    client = _build_client()
    r = client.get("/api/stations", params={"q": "36 Av"})
    assert r.status_code == 200
    body = r.json()
    assert any(s["stop_id"] == "R06" for s in body)


def test_http_limit():
    client = _build_client()
    r = client.get("/api/stations", params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_http_get_one():
    client = _build_client()
    r = client.get("/api/stations/R06")
    assert r.status_code == 200
    assert r.json()["name"] == "36 Av"


def test_http_get_unknown_404():
    client = _build_client()
    r = client.get("/api/stations/ZZZ999")
    assert r.status_code == 404
    assert r.json() == {"error": "unknown_station"}
