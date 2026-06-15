"""Tests for the layered runtime config store.

Tests point ``config_store.SETTINGS_PATH`` at a ``tmp_path`` file (monkeypatch)
and call ``_reset_for_tests()`` to clear the mtime cache between runs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app import config_store


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the overrides file to a tmp path and clear the mtime cache."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", path)
    config_store._reset_for_tests()
    yield path
    config_store._reset_for_tests()


# ---------------------------------------------------------------------------
# Defaults / shape
# ---------------------------------------------------------------------------
def test_defaults_when_no_file(settings_path: Path):
    cfg = config_store.get_runtime_config()
    assert set(cfg) == {"time", "weather", "photos", "trains"}
    assert cfg["time"]["timezone"] == "America/New_York"
    assert cfg["time"]["clock_24h"] is False
    assert isinstance(cfg["weather"]["lat"], float)
    assert isinstance(cfg["weather"]["lon"], float)
    assert cfg["weather"]["label"] == ""
    assert cfg["weather"]["user_agent"]
    assert isinstance(cfg["photos"]["directory"], str)
    assert cfg["trains"]["routes"] == ["N", "W"]
    assert cfg["trains"]["station_stop_id"]
    assert not settings_path.exists()  # reading never writes


def test_defaults_read_live_settings(settings_path, monkeypatch):
    # Monkeypatching the Settings singleton must flow through to defaults.
    monkeypatch.setattr(config_store.settings, "weather_lat", 12.5)
    cfg = config_store.get_runtime_config()
    assert cfg["weather"]["lat"] == 12.5


# ---------------------------------------------------------------------------
# Override merge
# ---------------------------------------------------------------------------
def test_override_merge(settings_path: Path):
    config_store.update_runtime_config({"weather": {"label": "Astoria 11106"}})
    cfg = config_store.get_runtime_config()
    assert cfg["weather"]["label"] == "Astoria 11106"
    # Other weather fields preserved from defaults.
    assert "lat" in cfg["weather"]


def test_partial_patch_does_not_clobber_other_sections(settings_path: Path):
    config_store.update_runtime_config({"time": {"clock_24h": True}})
    config_store.update_runtime_config({"trains": {"routes": ["Q"]}})
    cfg = config_store.get_runtime_config()
    # First patch survives the second.
    assert cfg["time"]["clock_24h"] is True
    assert cfg["trains"]["routes"] == ["Q"]
    # Untouched sections still at defaults.
    assert cfg["weather"]["label"] == ""


def test_atomic_write_produces_valid_json(settings_path: Path):
    config_store.update_runtime_config({"photos": {"directory": "/tmp/pics"}})
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    assert data["photos"]["directory"] == "/tmp/pics"
    # No leftover temp files in the directory.
    leftovers = [p.name for p in settings_path.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_invalid_timezone_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="timezone"):
        config_store.update_runtime_config({"time": {"timezone": "Mars/Phobos"}})
    assert not settings_path.exists()  # rejected patches are not persisted


def test_invalid_lat_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="lat"):
        config_store.update_runtime_config({"weather": {"lat": 999}})


def test_invalid_lon_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="lon"):
        config_store.update_runtime_config({"weather": {"lon": -200}})


def test_empty_photo_dir_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="directory"):
        config_store.update_runtime_config({"photos": {"directory": "  "}})


def test_invalid_routes_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="routes"):
        config_store.update_runtime_config({"trains": {"routes": "NW"}})


def test_empty_stop_id_rejected(settings_path: Path):
    with pytest.raises(ValueError, match="station_stop_id"):
        config_store.update_runtime_config({"trains": {"station_stop_id": ""}})


# ---------------------------------------------------------------------------
# Live re-read on mtime change
# ---------------------------------------------------------------------------
def test_live_reread_on_mtime_change(settings_path: Path):
    config_store.update_runtime_config({"weather": {"label": "first"}})
    assert config_store.get_runtime_config()["weather"]["label"] == "first"

    # Externally edit the file (simulating another writer). Bump mtime so the
    # cache invalidates even on coarse-grained filesystem clocks.
    time.sleep(0.01)
    settings_path.write_text(json.dumps({"weather": {"label": "second"}}))
    import os

    future = time.time() + 5
    os.utime(settings_path, (future, future))

    assert config_store.get_runtime_config()["weather"]["label"] == "second"
