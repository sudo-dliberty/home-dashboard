"""Settings router — read/write the layered runtime config.

``GET /api/settings`` returns the effective config; ``PUT /api/settings``
accepts a full or partial config object, validates + persists it, and returns
the new effective config. No auth: the backend is documented as 127.0.0.1-only.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from . import config_store

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return config_store.get_runtime_config()


@router.put("/settings")
async def put_settings(patch: dict[str, Any] = Body(...)) -> Any:
    # Accept a permissive dict; config_store does the real validation so the
    # error messages are per-field and consistent with file-driven validation.
    try:
        return config_store.update_runtime_config(patch)
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_settings", "detail": str(exc)},
        )
