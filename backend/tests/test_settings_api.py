"""Tests for the /api/settings router."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config_store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate the overrides file per test so GET/PUT don't touch the repo root."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", path)
    config_store._reset_for_tests()
    yield path
    config_store._reset_for_tests()


def test_get_returns_effective_shape():
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"time", "weather", "photos", "trains"}
    assert "timezone" in body["time"]
    assert "lat" in body["weather"] and "lon" in body["weather"]
    assert "directory" in body["photos"]
    assert "routes" in body["trains"]


def test_put_valid_persists_and_reflected_in_get(settings_path: Path):
    r = client.put(
        "/api/settings",
        json={"time": {"clock_24h": True}, "weather": {"label": "Astoria 11106"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["time"]["clock_24h"] is True
    assert body["weather"]["label"] == "Astoria 11106"

    # Persisted on disk and visible to a fresh GET.
    assert settings_path.exists()
    r2 = client.get("/api/settings")
    assert r2.json()["weather"]["label"] == "Astoria 11106"
    assert r2.json()["time"]["clock_24h"] is True


def test_put_invalid_returns_422(settings_path: Path):
    r = client.put("/api/settings", json={"time": {"timezone": "Nowhere/Land"}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_settings"
    assert "timezone" in body["detail"]
    # Nothing persisted on a rejected write.
    assert not settings_path.exists()
