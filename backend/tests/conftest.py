"""Shared test fixtures.

Isolates every test from a *real* ``settings.json`` at the repo root. That file
exists in normal use (the settings UI writes it), and several endpoints read the
runtime config — without this, a developer's saved location/station would leak
into tests and break assertions that assume the seed defaults.

Tests that exercise overrides (config store, settings API, trains) re-point
``SETTINGS_PATH`` to their own temp file on top of this; ``monkeypatch`` stacks
and unwinds cleanly.
"""
from __future__ import annotations

import pytest

from app import config_store


@pytest.fixture(autouse=True)
def _isolate_settings_json(tmp_path, monkeypatch):
    overrides = tmp_path / "settings.json"  # absent → pure seed defaults
    monkeypatch.setattr(config_store, "SETTINGS_PATH", overrides)
    config_store._reset_for_tests()
    yield
    config_store._reset_for_tests()
