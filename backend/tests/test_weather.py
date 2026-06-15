"""Tests for /api/weather.

Mocks NWS and Open-Meteo via respx so we never touch the network.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import weather as weather_mod
from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
client = TestClient(app)

NWS_POINTS_URL = "https://api.weather.gov/points/40.7568,-73.9296"
NWS_FORECAST_HOURLY_URL = (
    "https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly"
)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _make_nws_periods(
    n: int = 14,
    *,
    base_temp: int = 70,
    base_precip: int = 10,
    start: datetime | None = None,
) -> list[dict[str, Any]]:
    if start is None:
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    periods = []
    for i in range(n):
        t = start + timedelta(hours=i)
        periods.append(
            {
                "number": i + 1,
                "startTime": t.isoformat(),
                "endTime": (t + timedelta(hours=1)).isoformat(),
                "isDaytime": True,
                "temperature": base_temp + i,
                "temperatureUnit": "F",
                "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": base_precip + i},
                "shortForecast": "Partly Cloudy",
                "icon": "https://api.weather.gov/icons/land/day/few?size=medium",
            }
        )
    return periods


def _nws_points_response() -> dict[str, Any]:
    return {
        "properties": {
            "forecast": "https://api.weather.gov/gridpoints/OKX/33,35/forecast",
            "forecastHourly": NWS_FORECAST_HOURLY_URL,
            "forecastZone": "https://api.weather.gov/zones/forecast/NYZ072",
        }
    }


def _nws_hourly_response(**kwargs: Any) -> dict[str, Any]:
    return {"properties": {"periods": _make_nws_periods(**kwargs)}}


def _open_meteo_response(
    *,
    n: int = 14,
    base_temp: int = 55,
    base_precip: int = 50,
) -> dict[str, Any]:
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    return {
        "current": {
            "time": times[0],
            "temperature_2m": float(base_temp),
            "precipitation": 0.0,
            "weather_code": 2,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [float(base_temp + i) for i in range(n)],
            "precipitation_probability": [base_precip + i for i in range(n)],
            "weather_code": [2] * n,
        },
    }


@pytest.fixture(autouse=True)
def _reset_weather_cache():
    """Reset module-level caches between tests."""
    weather_mod._clear_cache()
    yield
    weather_mod._clear_cache()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@respx.mock
def test_nws_path():
    points = respx.get(NWS_POINTS_URL).mock(
        return_value=httpx.Response(200, json=_nws_points_response())
    )
    hourly = respx.get(NWS_FORECAST_HOURLY_URL).mock(
        return_value=httpx.Response(
            200,
            json=_nws_hourly_response(base_temp=70, base_precip=15),
        )
    )

    resp = client.get("/api/weather")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "nws"
    assert "fetched_at" in body
    assert "current" in body
    assert body["current"]["condition"] == "Partly Cloudy"
    assert body["current"]["icon"] == "few-clouds-day"
    assert body["current"]["temp_f"] == 70
    assert body["current"]["precip_prob"] == 15
    assert len(body["hourly"]) == 12
    # Spot-check first/last hourly entries.
    assert body["hourly"][0]["temp_f"] == 70
    assert body["hourly"][11]["temp_f"] == 81
    # Summary: temps 70..81 → no coat; precip 15..26 → no umbrella.
    summary = body["summary"]
    assert summary["needs_coat"] is False
    assert summary["needs_umbrella"] is False
    assert summary["min_temp_next_12h_f"] == 70
    assert summary["max_precip_prob_next_12h"] == 26

    assert points.called
    assert hourly.called


@respx.mock
def test_open_meteo_fallback():
    respx.get(NWS_POINTS_URL).mock(return_value=httpx.Response(500))
    om = respx.get(url__startswith=OPEN_METEO_URL).mock(
        return_value=httpx.Response(200, json=_open_meteo_response(base_temp=60, base_precip=20))
    )

    resp = client.get("/api/weather")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "open-meteo"
    assert body["current"]["condition"] == "Partly Cloudy"
    assert body["current"]["icon"] == "wmo-2"
    assert len(body["hourly"]) == 12
    assert om.called


@respx.mock
def test_cache_hit_avoids_upstream():
    points = respx.get(NWS_POINTS_URL).mock(
        return_value=httpx.Response(200, json=_nws_points_response())
    )
    hourly = respx.get(NWS_FORECAST_HOURLY_URL).mock(
        return_value=httpx.Response(200, json=_nws_hourly_response())
    )

    r1 = client.get("/api/weather")
    assert r1.status_code == 200
    first_call_count = points.call_count + hourly.call_count
    assert first_call_count == 2  # one points + one forecastHourly

    r2 = client.get("/api/weather")
    assert r2.status_code == 200
    # Same number of upstream calls — second response served from cache.
    assert points.call_count + hourly.call_count == first_call_count
    # And the payload is identical (cache returns same dict contents).
    assert r1.json()["fetched_at"] == r2.json()["fetched_at"]


@respx.mock
def test_stale_when_both_providers_fail_with_cache():
    # Populate cache via a successful first call.
    respx.get(NWS_POINTS_URL).mock(
        return_value=httpx.Response(200, json=_nws_points_response())
    )
    hourly_route = respx.get(NWS_FORECAST_HOURLY_URL).mock(
        return_value=httpx.Response(200, json=_nws_hourly_response())
    )

    r1 = client.get("/api/weather")
    assert r1.status_code == 200
    assert r1.json()["provider"] == "nws"
    assert "stale" not in r1.json()

    # Now expire the response cache (but keep the forecastHourly URL cache —
    # that simulates a real "more than 5 min later" scenario).
    weather_mod._response_cache["payload"] = r1.json()
    weather_mod._response_cache["timestamp"] = 0.0  # ancient → not fresh

    # Replace mocks: both providers fail.
    hourly_route.mock(return_value=httpx.Response(500))
    respx.get(url__startswith=OPEN_METEO_URL).mock(return_value=httpx.Response(500))

    r2 = client.get("/api/weather")
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("stale") is True
    assert body["provider"] == "nws"  # echoed from cached payload


@respx.mock
def test_503_when_both_fail_no_cache():
    respx.get(NWS_POINTS_URL).mock(return_value=httpx.Response(500))
    respx.get(url__startswith=OPEN_METEO_URL).mock(return_value=httpx.Response(500))

    resp = client.get("/api/weather")
    assert resp.status_code == 503
    assert resp.json() == {"error": "weather_unavailable"}


def test_summary_thresholds():
    # Below 55 → needs_coat; precip >= 40 → needs_umbrella.
    cold_wet = [
        {"time": "2026-01-01T00:00:00Z", "temp_f": 60, "precip_prob": 10, "condition": "x"},
        {"time": "2026-01-01T01:00:00Z", "temp_f": 54, "precip_prob": 45, "condition": "x"},
        {"time": "2026-01-01T02:00:00Z", "temp_f": 58, "precip_prob": 20, "condition": "x"},
    ]
    s = weather_mod._summarize(cold_wet)
    assert s["needs_coat"] is True
    assert s["needs_umbrella"] is True
    assert s["min_temp_next_12h_f"] == 54
    assert s["max_precip_prob_next_12h"] == 45

    mild_dry = [
        {"time": "2026-01-01T00:00:00Z", "temp_f": 70, "precip_prob": 10, "condition": "x"},
        {"time": "2026-01-01T01:00:00Z", "temp_f": 65, "precip_prob": 39, "condition": "x"},
    ]
    s = weather_mod._summarize(mild_dry)
    assert s["needs_coat"] is False
    assert s["needs_umbrella"] is False
    assert s["min_temp_next_12h_f"] == 65
    assert s["max_precip_prob_next_12h"] == 39

    # Boundary: exactly 55 → no coat; exactly 40 → umbrella.
    boundary = [
        {"time": "2026-01-01T00:00:00Z", "temp_f": 55, "precip_prob": 40, "condition": "x"},
    ]
    s = weather_mod._summarize(boundary)
    assert s["needs_coat"] is False
    assert s["needs_umbrella"] is True


# ---------------------------------------------------------------------------
# /api/geocode — ZIP → lat/lon (Zippopotam.us), mocked
# ---------------------------------------------------------------------------
ZIPPO_URL = "https://api.zippopotam.us/us/11106"


@respx.mock
def test_geocode_valid_zip():
    respx.get(ZIPPO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "post code": "11106",
                "country": "United States",
                "places": [
                    {
                        "place name": "Astoria",
                        "state": "New York",
                        "state abbreviation": "NY",
                        "latitude": "40.7644",
                        "longitude": "-73.9235",
                    }
                ],
            },
        )
    )
    r = client.get("/api/geocode", params={"zip": "11106"})
    assert r.status_code == 200
    body = r.json()
    assert body["zip"] == "11106"
    assert body["lat"] == pytest.approx(40.7644)
    assert body["lon"] == pytest.approx(-73.9235)
    assert body["label"] == "Astoria, NY"


def test_geocode_malformed_zip_is_400():
    # Non-numeric / wrong length never hits the network.
    assert client.get("/api/geocode", params={"zip": "abc"}).status_code == 400
    assert client.get("/api/geocode", params={"zip": "123"}).status_code == 400


@respx.mock
def test_geocode_unknown_zip_is_404():
    respx.get("https://api.zippopotam.us/us/00000").mock(
        return_value=httpx.Response(404, json={})
    )
    r = client.get("/api/geocode", params={"zip": "00000"})
    assert r.status_code == 404
    assert r.json()["error"] == "zip_not_found"
