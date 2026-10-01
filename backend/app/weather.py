"""Weather router: NWS primary with Open-Meteo fallback.

Contract documented in PLAN.md section 4. Caches the merged response for
``settings.weather_cache_seconds`` (default 300 s). On total upstream failure
the cached value is returned with ``"stale": true``; if no cache exists, a 503
``{"error": "weather_unavailable"}`` response is returned.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import config_store
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["weather"])

NWS_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# Key-less US ZIP → lat/lon geocoder. Used only by the settings UI so users can
# type a ZIP instead of raw coordinates; the resolved lat/lon is what we persist.
ZIPPOPOTAM_URL = "https://api.zippopotam.us/us/{zip}"

_HTTP_TIMEOUT = 5.0
_HOURLY_WINDOW = 12  # entries the contract requires

# Module-level caches (process lifetime).
# _forecast_hourly_url_cache maps "lat,lon" -> the NWS forecastHourly URL,
# which is stable per coord per NWS docs.
_forecast_hourly_url_cache: dict[str, str] = {}

# _response_cache stores the most-recent successfully-built payload and the
# monotonic timestamp it was built at.
_response_cache: dict[str, Any] = {
    "payload": None,
    "timestamp": 0.0,
}


# ---------------------------------------------------------------------------
# WMO weather-code lookup (for Open-Meteo fallback)
# ---------------------------------------------------------------------------
# Reference: https://open-meteo.com/en/docs (WMO code table).
_WMO_CONDITIONS: dict[int, str] = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Light Freezing Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Hail",
    99: "Severe Thunderstorm",
}


def _wmo_condition(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return _WMO_CONDITIONS.get(int(code), f"WMO {code}")


def _wmo_icon(code: int | None) -> str:
    if code is None:
        return "wmo-unknown"
    return f"wmo-{int(code)}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nws_icon_token(icon_url: str | None) -> str:
    """Extract a stable identifier from an NWS icon URL.

    Example input:  https://api.weather.gov/icons/land/day/few?size=medium
    Example output: few-clouds-day
    """
    if not icon_url:
        return "unknown"
    try:
        path = urlparse(icon_url).path  # /icons/land/day/few
        parts = [p for p in path.split("/") if p]
        # parts = ["icons", "land", "day", "few"] (last segment may have comma:
        # e.g. "rain_showers,40").  Period-of-day is parts[-2] when present.
        condition = parts[-1].split(",")[0]
        period = parts[-2] if len(parts) >= 2 else ""
        # Friendly names for the common "few" / "sct" / "bkn" / "ovc" set.
        friendly = {
            "few": "few-clouds",
            "sct": "scattered-clouds",
            "bkn": "broken-clouds",
            "ovc": "overcast",
            "skc": "clear",
        }.get(condition, condition)
        if period in ("day", "night"):
            return f"{friendly}-{period}"
        return friendly
    except Exception:  # noqa: BLE001 - icon parsing is best-effort
        return "unknown"


def _coerce_precip(value: Any) -> int:
    """Return an int 0-100; treat None or unparseable as 0."""
    if value is None:
        return 0
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _summarize(hourly: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the ``summary`` block from the next-12h ``hourly`` list."""
    if not hourly:
        return {
            "needs_coat": False,
            "needs_umbrella": False,
            "min_temp_next_12h_f": None,
            "max_precip_prob_next_12h": 0,
        }
    temps = [h["temp_f"] for h in hourly if h.get("temp_f") is not None]
    precips = [h.get("precip_prob", 0) or 0 for h in hourly]
    min_temp = min(temps) if temps else None
    max_precip = max(precips) if precips else 0
    return {
        "needs_coat": (min_temp is not None and min_temp < 55),
        "needs_umbrella": max_precip >= 40,
        "min_temp_next_12h_f": min_temp,
        "max_precip_prob_next_12h": max_precip,
    }


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
async def _resolve_nws_forecast_hourly_url(
    client: httpx.AsyncClient, lat: float, lon: float
) -> str:
    """Return the NWS ``forecastHourly`` URL for ``(lat, lon)``, cached forever."""
    lat_r = round(lat, 4)
    lon_r = round(lon, 4)
    key = f"{lat_r},{lon_r}"
    cached = _forecast_hourly_url_cache.get(key)
    if cached:
        return cached
    url = NWS_POINTS_URL.format(lat=lat_r, lon=lon_r)
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    hourly_url = data["properties"]["forecastHourly"]
    _forecast_hourly_url_cache[key] = hourly_url
    return hourly_url


async def fetch_nws() -> dict[str, Any]:
    """Fetch + normalize the NWS forecast. Raises on any failure."""
    weather_cfg = config_store.get_runtime_config()["weather"]
    headers = {
        "User-Agent": weather_cfg["user_agent"],
        "Accept": "application/geo+json",
    }
    async with httpx.AsyncClient(headers=headers, timeout=_HTTP_TIMEOUT) as client:
        hourly_url = await _resolve_nws_forecast_hourly_url(
            client, weather_cfg["lat"], weather_cfg["lon"]
        )
        resp = await client.get(hourly_url)
        resp.raise_for_status()
        periods = resp.json()["properties"]["periods"]

    if not periods:
        raise ValueError("NWS forecastHourly returned no periods")

    first = periods[0]
    current = {
        "temp_f": int(round(float(first["temperature"]))),
        "feels_like_f": int(round(float(first["temperature"]))),
        "condition": first.get("shortForecast", "Unknown"),
        "icon": _nws_icon_token(first.get("icon")),
        "precip_prob": _coerce_precip(
            (first.get("probabilityOfPrecipitation") or {}).get("value")
        ),
    }

    hourly = []
    for p in periods[:_HOURLY_WINDOW]:
        hourly.append(
            {
                "time": p["startTime"],
                "temp_f": int(round(float(p["temperature"]))),
                "precip_prob": _coerce_precip(
                    (p.get("probabilityOfPrecipitation") or {}).get("value")
                ),
                "condition": p.get("shortForecast", "Unknown"),
            }
        )

    return {
        "fetched_at": _now_utc_iso(),
        "provider": "nws",
        "current": current,
        "hourly": hourly,
        "summary": _summarize(hourly),
    }


def _utc_iso(t: str) -> str:
    """Make an offset-less Open-Meteo UTC time an explicit ISO 8601 UTC time."""
    if t.endswith("Z") or "+" in t[10:] or "-" in t[10:]:
        return t
    return f"{t}:00Z" if len(t) == 16 else f"{t}Z"


async def fetch_open_meteo() -> dict[str, Any]:
    """Fetch + normalize the Open-Meteo forecast. Raises on any failure."""
    weather_cfg = config_store.get_runtime_config()["weather"]
    params = {
        "latitude": weather_cfg["lat"],
        "longitude": weather_cfg["lon"],
        "current": "temperature_2m,precipitation,weather_code",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "temperature_unit": "fahrenheit",
        # Ask for UTC so hourly times compare cleanly with "now" below and can
        # be emitted with an explicit "Z". Open-Meteo's local-time strings
        # carry no offset, which browsers would misread in their own zone.
        "timezone": "GMT",
        "forecast_days": 2,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current_block = data.get("current") or {}
    hourly_block = data.get("hourly") or {}
    times: list[str] = list(hourly_block.get("time", []) or [])
    temps: list[Any] = list(hourly_block.get("temperature_2m", []) or [])
    probs: list[Any] = list(hourly_block.get("precipitation_probability", []) or [])
    codes: list[Any] = list(hourly_block.get("weather_code", []) or [])

    if not times:
        raise ValueError("Open-Meteo hourly block is empty")

    # Start the 12h window at the current UTC hour. Times are UTC
    # "YYYY-MM-DDTHH:MM" strings, so a YYYY-MM-DDTHH prefix compare is exact.
    now_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    start_idx = 0
    for i, t in enumerate(times):
        if t[:13] >= now_hour:
            start_idx = i
            break

    hourly: list[dict[str, Any]] = []
    for i in range(start_idx, min(start_idx + _HOURLY_WINDOW, len(times))):
        temp = temps[i] if i < len(temps) else None
        prob = probs[i] if i < len(probs) else None
        code = codes[i] if i < len(codes) else None
        if temp is None:
            continue
        hourly.append(
            {
                "time": _utc_iso(times[i]),
                "temp_f": int(round(float(temp))),
                "precip_prob": _coerce_precip(prob),
                "condition": _wmo_condition(code),
            }
        )

    cur_temp = current_block.get("temperature_2m")
    cur_code = current_block.get("weather_code")
    current = {
        "temp_f": int(round(float(cur_temp))) if cur_temp is not None else (
            hourly[0]["temp_f"] if hourly else 0
        ),
        "feels_like_f": int(round(float(cur_temp))) if cur_temp is not None else (
            hourly[0]["temp_f"] if hourly else 0
        ),
        "condition": _wmo_condition(cur_code),
        "icon": _wmo_icon(cur_code),
        "precip_prob": hourly[0]["precip_prob"] if hourly else 0,
    }

    return {
        "fetched_at": _now_utc_iso(),
        "provider": "open-meteo",
        "current": current,
        "hourly": hourly,
        "summary": _summarize(hourly),
    }


# ---------------------------------------------------------------------------
# Cache control (also useful for tests)
# ---------------------------------------------------------------------------
def _clear_cache() -> None:
    """Reset all module-level caches. Intended for tests."""
    _forecast_hourly_url_cache.clear()
    _response_cache["payload"] = None
    _response_cache["timestamp"] = 0.0


def _cache_fresh() -> bool:
    if _response_cache["payload"] is None:
        return False
    age = time.monotonic() - _response_cache["timestamp"]
    return age < settings.weather_cache_seconds


def _store_cache(payload: dict[str, Any]) -> None:
    _response_cache["payload"] = payload
    _response_cache["timestamp"] = time.monotonic()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
@router.get("/weather")
async def get_weather() -> Any:
    # 1) Serve from cache if still fresh.
    if _cache_fresh():
        # dict() to avoid leaking the same reference (some tests will mutate).
        return dict(_response_cache["payload"])  # type: ignore[arg-type]

    # 2) Try NWS first.
    try:
        payload = await fetch_nws()
        _store_cache(payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - upstream errors of any kind
        logger.warning("NWS fetch failed: %s", exc)

    # 3) Try Open-Meteo fallback.
    try:
        payload = await fetch_open_meteo()
        _store_cache(payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("Open-Meteo fetch failed: %s", exc)

    # 4) Both providers failed.  Serve stale cache if we have anything.
    cached = _response_cache["payload"]
    if cached is not None:
        stale = dict(cached)
        stale["stale"] = True
        return stale

    return JSONResponse(
        status_code=503,
        content={"error": "weather_unavailable"},
    )


@router.get("/geocode")
async def geocode_zip(zip: str = "") -> Any:
    """Resolve a US ZIP code to ``{zip, lat, lon, label}`` via Zippopotam.us.

    A convenience for the settings UI so users can enter a familiar ZIP instead
    of raw coordinates. Returns 400 for a malformed ZIP and 404 when the ZIP is
    unknown or the lookup fails — the UI keeps the existing lat/lon in that case.
    """
    z = (zip or "").strip()
    if not (len(z) == 5 and z.isdigit()):
        return JSONResponse(status_code=400, content={"error": "invalid_zip"})

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(ZIPPOPOTAM_URL.format(zip=z))
            resp.raise_for_status()
            data = resp.json()
        place = (data.get("places") or [{}])[0]
        lat = float(place["latitude"])
        lon = float(place["longitude"])
        city = place.get("place name", "")
        state = place.get("state abbreviation") or place.get("state", "")
        label = ", ".join(p for p in (city, state) if p)
        return {"zip": z, "lat": lat, "lon": lon, "label": label}
    except Exception as exc:  # noqa: BLE001 - upstream/parse errors of any kind
        logger.warning("ZIP geocode failed for %s: %s", z, exc)
        return JSONResponse(status_code=404, content={"error": "zip_not_found"})
