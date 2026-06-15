"""Layered runtime configuration store.

Effective config = pydantic ``Settings`` seed defaults deep-merged with runtime
overrides persisted in a gitignored ``settings.json`` at the repo root.

Design notes:
- Seed defaults are read from the *live* ``settings`` singleton **at call time**
  (never snapshotted at import) so existing tests that monkeypatch
  ``settings.weather_lat`` / ``settings.photo_dir`` still influence the effective
  config when no override is present.
- ``settings.json`` is read live but cached by file mtime, so callers can hit it
  per-request cheaply while still picking up external edits.
- Writes are atomic (temp file in the same dir + ``os.replace``).

Tests override the file location by monkeypatching the module-level
``SETTINGS_PATH`` constant (and calling ``_reset_for_tests()`` to drop the mtime
cache). See ``tests/test_config_store.py``.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import available_timezones

from .config import _REPO_ROOT, settings

# Runtime overrides live next to .env at the repo root. Module-level so tests can
# monkeypatch it to a tmp_path.
SETTINGS_PATH: Path = _REPO_ROOT / "settings.json"

# mtime-keyed cache of the parsed overrides. ``None`` mtime means "not yet read"
# or "file absent". We re-read whenever the on-disk mtime differs.
_cache: dict[str, Any] = {"mtime": None, "overrides": {}}


class ConfigValidationError(ValueError):
    """Raised when a settings patch fails validation.

    Subclasses ``ValueError`` so the settings router can catch either; the
    message is a clear per-field string suitable for an HTTP 422 ``detail``.
    """


# ---------------------------------------------------------------------------
# Defaults (read live from the Settings singleton)
# ---------------------------------------------------------------------------
def _default_config() -> dict[str, Any]:
    """Build the effective-config skeleton from current ``settings`` values.

    Read at call time (not import) so monkeypatched Settings attributes are
    honored by tests and any future hot-reload of Settings.
    """
    return {
        "time": {
            "timezone": settings.timezone,
            "clock_24h": settings.clock_24h,
        },
        "weather": {
            "lat": float(settings.weather_lat),
            "lon": float(settings.weather_lon),
            "label": "",
            "zip": "",  # optional US ZIP; resolved to lat/lon via /api/geocode
            "user_agent": settings.weather_user_agent,
        },
        "photos": {
            "directory": str(settings.photo_dir),
        },
        "trains": {
            "station_stop_id": settings.station_stop_id,
            "routes": ["N", "W"],
        },
    }


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------
def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``patch`` into a copy of ``base`` and return it.

    Nested dicts merge key-by-key; everything else (scalars, lists) is replaced
    wholesale by the patch value.
    """
    result = dict(base)
    for key, value in patch.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Overrides file IO (mtime-cached read, atomic write)
# ---------------------------------------------------------------------------
def _load_overrides() -> dict[str, Any]:
    """Return parsed overrides from ``settings.json``, cached by mtime.

    Absent or unreadable file → ``{}``. A corrupt file is treated as no
    overrides rather than crashing the dashboard.
    """
    try:
        mtime = SETTINGS_PATH.stat().st_mtime
    except FileNotFoundError:
        _cache["mtime"] = None
        _cache["overrides"] = {}
        return {}

    if _cache["mtime"] == mtime:
        return _cache["overrides"]

    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        overrides = data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        overrides = {}

    _cache["mtime"] = mtime
    _cache["overrides"] = overrides
    return overrides


def _write_overrides(overrides: dict[str, Any]) -> None:
    """Atomically persist ``overrides`` to ``settings.json``.

    Writes a temp file in the same directory then ``os.replace`` so readers
    never observe a half-written file.
    """
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(SETTINGS_PATH.parent), prefix=".settings.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(overrides, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, SETTINGS_PATH)
    except BaseException:
        # Clean up the temp file on any failure so we don't litter the repo root.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    # Refresh the cache to the just-written state.
    _cache["mtime"] = SETTINGS_PATH.stat().st_mtime
    _cache["overrides"] = overrides


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate_effective(config: dict[str, Any]) -> None:
    """Validate a *fully merged* effective config; raise on the first problem.

    Validating the merged result (not just the patch) keeps every persisted
    state internally consistent regardless of which subset a patch touched.
    """
    time_cfg = config.get("time", {})
    tz = time_cfg.get("timezone")
    if not isinstance(tz, str) or tz not in available_timezones():
        raise ConfigValidationError(
            f"time.timezone: {tz!r} is not a valid IANA timezone"
        )
    if not isinstance(time_cfg.get("clock_24h"), bool):
        raise ConfigValidationError("time.clock_24h: must be a boolean")

    weather = config.get("weather", {})
    lat = weather.get("lat")
    lon = weather.get("lon")
    if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not (-90 <= lat <= 90):
        raise ConfigValidationError("weather.lat: must be a number in [-90, 90]")
    if not isinstance(lon, (int, float)) or isinstance(lon, bool) or not (-180 <= lon <= 180):
        raise ConfigValidationError("weather.lon: must be a number in [-180, 180]")
    zip_code = weather.get("zip")
    if zip_code is not None and not isinstance(zip_code, str):
        raise ConfigValidationError("weather.zip: must be a string")

    photos = config.get("photos", {})
    directory = photos.get("directory")
    if not isinstance(directory, str) or not directory.strip():
        raise ConfigValidationError("photos.directory: must be a non-empty string")

    trains = config.get("trains", {})
    stop_id = trains.get("station_stop_id")
    if not isinstance(stop_id, str) or not stop_id.strip():
        raise ConfigValidationError(
            "trains.station_stop_id: must be a non-empty string"
        )
    routes = trains.get("routes")
    if not isinstance(routes, list) or not all(
        isinstance(r, str) and 0 < len(r) <= 3 for r in routes
    ):
        raise ConfigValidationError(
            "trains.routes: must be a list of short route strings"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_runtime_config() -> dict[str, Any]:
    """Return the effective config: live defaults deep-merged with overrides."""
    return _deep_merge(_default_config(), _load_overrides())


def update_runtime_config(patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``patch`` into existing overrides, validate, persist, return.

    Validation runs against the resulting *effective* config so callers can send
    any subset of sections. On success the merged overrides are written
    atomically and the new effective config is returned.
    """
    if not isinstance(patch, dict):
        raise ConfigValidationError("settings: body must be a JSON object")

    current_overrides = _load_overrides()
    new_overrides = _deep_merge(current_overrides, patch)
    effective = _deep_merge(_default_config(), new_overrides)
    _validate_effective(effective)
    _write_overrides(new_overrides)
    return effective


def _reset_for_tests() -> None:
    """Drop the mtime cache. Pair with monkeypatching ``SETTINGS_PATH``."""
    _cache["mtime"] = None
    _cache["overrides"] = {}
