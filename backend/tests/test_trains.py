"""Tests for the /api/trains endpoint and the GTFS-realtime parser.

The endpoint is now driven by runtime config (``config_store``), so each test
writes a temp ``settings.json`` selecting station ``R06`` with routes ``N``/``W``
— exactly what the captured NQRW fixture covers — and points
``config_store.SETTINGS_PATH`` at it (with ``_reset_for_tests`` to drop the
mtime cache). Feed fetches are mocked per feed URL via respx.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2

from app import config_store
from app import trains as trains_mod
from app.config import settings
from app.main import app
from app.trains import parse_feeds

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nqrw_sample.pb"

# The fixture is the NQRW feed; route N/W both map to this single feed URL.
NQRW_FEED_URL = settings.mta_nqrw_feed_url


def _load_fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def _fixture_baseline_now() -> datetime:
    """Choose a sensible ``now`` for the captured fixture: the earliest
    ``R06N``/``R06S`` arrival time minus a minute, so several arrivals remain in
    the [1, 30] minute window."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(_load_fixture_bytes())
    times: list[int] = []
    for e in feed.entity:
        if not e.HasField("trip_update"):
            continue
        tu = e.trip_update
        if tu.trip.route_id not in ("N", "W"):
            continue
        for stu in tu.stop_time_update:
            if stu.stop_id in ("R06N", "R06S"):
                t = 0
                if stu.HasField("arrival") and stu.arrival.time:
                    t = stu.arrival.time
                elif stu.HasField("departure") and stu.departure.time:
                    t = stu.departure.time
                if t:
                    times.append(t)
    assert times, "fixture has no R06 arrivals — unusable"
    baseline = min(times) - 60  # 1 minute before the earliest arrival
    return datetime.fromtimestamp(baseline, tz=timezone.utc)


@pytest.fixture(autouse=True)
def _runtime_config_r06(tmp_path, monkeypatch):
    """Point runtime config at station R06 / routes N,W via a temp settings.json,
    and reset the per-feed cache around each test."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"trains": {"station_stop_id": "R06", "routes": ["N", "W"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "SETTINGS_PATH", settings_path)
    config_store._reset_for_tests()

    trains_mod._reset_cache_for_tests()
    yield
    trains_mod._reset_cache_for_tests()
    config_store._reset_for_tests()


def test_parse_fixture_structure():
    now = _fixture_baseline_now()
    parsed = parse_feeds(
        [_load_fixture_bytes()],
        station_stop_id="R06",
        routes={"N", "W"},
        now=now,
    )

    north = parsed["north"]
    south = parsed["south"]
    assert isinstance(north, list) and isinstance(south, list)
    # The fixture has arrivals near the chosen now, so at least one bound must
    # be non-empty.
    assert (north or south), "expected at least one arrival in window"

    for arrivals in (north, south):
        # sorted ascending by minutes
        mins = [a["minutes"] for a in arrivals]
        assert mins == sorted(mins)
        for a in arrivals:
            assert a["route"] in {"N", "W"}
            assert 1 <= a["minutes"] <= settings.train_max_minutes
            # arrival ISO 8601 UTC with trailing Z
            assert a["arrival"].endswith("Z")


def test_endpoint_returns_fresh(monkeypatch):
    feed_bytes = _load_fixture_bytes()
    now = _fixture_baseline_now()

    # Pin the parser/clock to the fixture's time so arrivals fall in range.
    monkeypatch.setattr(trains_mod, "_utc_now", lambda: now)

    with respx.mock(assert_all_called=True) as router:
        router.get(NQRW_FEED_URL).mock(
            return_value=httpx.Response(200, content=feed_bytes)
        )
        with TestClient(app) as client:
            r = client.get("/api/trains")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["station"] == "36 Av"
    assert body["stop_id"] == "R06"
    assert body["stale"] is False
    assert body["fetched_at"].endswith("Z")
    assert isinstance(body["feed_age_s"], int)
    assert body["feed_age_s"] >= 0

    # Directional shape: {label, arrivals}.
    for side in ("north", "south"):
        assert set(body[side].keys()) == {"label", "arrivals"}
        assert isinstance(body[side]["label"], str)
        assert isinstance(body[side]["arrivals"], list)

    # Labels come from the registry, not hardcoded.
    assert body["north"]["label"]
    assert body["south"]["label"]

    # Contract shape on items.
    items = body["north"]["arrivals"] + body["south"]["arrivals"]
    assert items, "expected at least one arrival in window"
    for item in items:
        assert set(item.keys()) == {"route", "minutes", "arrival"}
        assert item["route"] in {"N", "W"}
        assert 1 <= item["minutes"] <= settings.train_max_minutes
        assert item["arrival"].endswith("Z")


def test_endpoint_stale_on_upstream_failure(monkeypatch):
    feed_bytes = _load_fixture_bytes()
    now = _fixture_baseline_now()
    monkeypatch.setattr(trains_mod, "_utc_now", lambda: now)

    # First call: success — populates the cache.
    with respx.mock() as router:
        router.get(NQRW_FEED_URL).mock(
            return_value=httpx.Response(200, content=feed_bytes)
        )
        with TestClient(app) as client:
            r1 = client.get("/api/trains")
    assert r1.status_code == 200
    fresh_body = r1.json()
    assert fresh_body["stale"] is False

    # Advance "now" past the cache TTL so the next call attempts a refresh.
    later = datetime.fromtimestamp(
        now.timestamp() + settings.train_feed_cache_seconds + 5,
        tz=timezone.utc,
    )
    monkeypatch.setattr(trains_mod, "_utc_now", lambda: later)

    # Second call: upstream 500. Should serve stale cache with 200.
    with respx.mock() as router:
        router.get(NQRW_FEED_URL).mock(return_value=httpx.Response(500))
        with TestClient(app) as client:
            r2 = client.get("/api/trains")

    assert r2.status_code == 200, r2.text
    stale_body = r2.json()
    assert stale_body["stale"] is True
    # Same cached data (same arrivals + same fetched_at).
    assert stale_body["fetched_at"] == fresh_body["fetched_at"]
    assert stale_body["north"]["arrivals"] == fresh_body["north"]["arrivals"]
    assert stale_body["south"]["arrivals"] == fresh_body["south"]["arrivals"]
    # feed_age_s should have grown.
    assert stale_body["feed_age_s"] >= fresh_body["feed_age_s"]


def test_endpoint_503_without_cache():
    # Cache was reset by the autouse fixture. First call hits 500 with no
    # fallback → 503.
    with respx.mock() as router:
        router.get(NQRW_FEED_URL).mock(return_value=httpx.Response(500))
        with TestClient(app) as client:
            r = client.get("/api/trains")

    assert r.status_code == 503
    assert r.json() == {"error": "feed_unavailable"}


def test_filters_other_routes():
    """An R-train arrival at R06N (an upstream-data artifact) must be excluded."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(time.time())

    # Use a known reference time so the math is deterministic.
    now = datetime(2026, 5, 31, 18, 0, 0, tzinfo=timezone.utc)
    base = int(now.timestamp())

    # Entity 1: R-train at R06N in 5 min — must be excluded.
    e1 = feed.entity.add()
    e1.id = "trip-R-1"
    e1.trip_update.trip.trip_id = "R-trip-1"
    e1.trip_update.trip.route_id = "R"
    stu_r = e1.trip_update.stop_time_update.add()
    stu_r.stop_id = "R06N"
    stu_r.arrival.time = base + 5 * 60

    # Entity 2: N-train at R06N in 7 min — must be included.
    e2 = feed.entity.add()
    e2.id = "trip-N-1"
    e2.trip_update.trip.trip_id = "N-trip-1"
    e2.trip_update.trip.route_id = "N"
    stu_n = e2.trip_update.stop_time_update.add()
    stu_n.stop_id = "R06N"
    stu_n.arrival.time = base + 7 * 60

    # Entity 3: Q-train at R06S in 4 min — must be excluded.
    e3 = feed.entity.add()
    e3.id = "trip-Q-1"
    e3.trip_update.trip.trip_id = "Q-trip-1"
    e3.trip_update.trip.route_id = "Q"
    stu_q = e3.trip_update.stop_time_update.add()
    stu_q.stop_id = "R06S"
    stu_q.arrival.time = base + 4 * 60

    # Entity 4: W-train at R06S in 12 min — must be included.
    e4 = feed.entity.add()
    e4.id = "trip-W-1"
    e4.trip_update.trip.trip_id = "W-trip-1"
    e4.trip_update.trip.route_id = "W"
    stu_w = e4.trip_update.stop_time_update.add()
    stu_w.stop_id = "R06S"
    stu_w.arrival.time = base + 12 * 60

    parsed = parse_feeds(
        [feed.SerializeToString()],
        station_stop_id="R06",
        routes={"N", "W"},
        now=now,
    )
    north_routes = [a["route"] for a in parsed["north"]]
    south_routes = [a["route"] for a in parsed["south"]]

    assert "R" not in north_routes
    assert "Q" not in south_routes
    assert north_routes == ["N"]
    assert south_routes == ["W"]
    # And the included ones carry the right minute values.
    assert parsed["north"][0]["minutes"] == 7
    assert parsed["south"][0]["minutes"] == 12
