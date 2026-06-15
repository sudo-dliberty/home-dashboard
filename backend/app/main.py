from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from .config import settings
from .photos import router as photos_router
from .settings_api import router as settings_router
from .stations import router as stations_router
from .trains import router as trains_router
from .weather import router as weather_router

_START_TIME = time.monotonic()


class SPAStaticFiles(StaticFiles):
    """StaticFiles that never lets the entry HTML go stale.

    Vite content-hashes every built asset filename, so /assets/* is safe to
    cache forever — but index.html (served with no hash, at every unmatched
    path too, since html=True) referencing those hashes must always be
    revalidated. Without this, a browser with no explicit Cache-Control
    falls back to heuristic caching and can keep serving an old index.html
    — and therefore old, since-deleted JS — indefinitely across restarts,
    long after a new build has been deployed. On a kiosk that never does a
    user-initiated hard refresh, that stale JS eventually throws an
    uncaught exception with no error boundary to catch it, which blanks the
    whole page to the black background from index.html's own inline CSS.
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

app = FastAPI(title="Astoria Home Dashboard", version="0.1.0")

# CORS open in dev so the Vite dev server can hit /api during development.
# In production the SPA is served from the same origin, so this is a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(trains_router)
app.include_router(weather_router)
app.include_router(photos_router)
app.include_router(settings_router)
app.include_router(stations_router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "uptime_s": round(time.monotonic() - _START_TIME, 1),
        "station_stop_id": settings.station_stop_id,
    }


# Serve the built SPA last so /api/* routes win.
if settings.static_dir and settings.static_dir.is_dir():
    app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="spa")
