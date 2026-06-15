from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (one level above backend/). Pin to an absolute
# path so the settings work regardless of which directory uvicorn runs from.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MTA / trains
    mta_nqrw_feed_url: str = Field(
        default="https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw"
    )
    station_stop_id: str = Field(default="R06")  # 36 Av (Astoria)
    train_max_minutes: int = Field(default=30)
    train_feed_cache_seconds: int = Field(default=15)

    # Weather
    weather_lat: float = Field(default=40.7568)
    weather_lon: float = Field(default=-73.9296)
    weather_user_agent: str = Field(
        default="home-dashboard (local, you@example.com)"
    )
    weather_cache_seconds: int = Field(default=300)

    # Photos
    photo_dir: Path = Field(default=Path.home() / "Pictures" / "dashboard")
    photo_heic: bool = Field(default=False)

    # Time / clock (seed defaults; user-tunable at runtime via settings.json)
    timezone: str = Field(default="America/New_York")
    clock_24h: bool = Field(default=False)

    # Server
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    static_dir: Path | None = Field(default=None)  # set in prod to serve built SPA


settings = Settings()
