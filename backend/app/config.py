"""Ilova sozlamalari. Hamma qiymat .env yoki muhit o'zgaruvchilaridan o'qiladi."""

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = ""
    bot_mode: Literal["polling", "webhook"] = "polling"
    webhook_base_url: str = ""
    webhook_secret: str = ""

    # Yengil rejim (Docker, PostgreSQL va Redis'siz): SQLite fayl, xotiradagi kesh va FSM,
    # Celery o'rniga API jarayonining ichidagi jadval. Bitta kompyuterda sinash uchun.
    lite_mode: bool = False

    # Infratuzilma
    database_url: str = "postgresql+asyncpg://havo:change-me@localhost:5432/havo"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""

    # Havo ma'lumoti
    air_provider: Literal["openweathermap"] = "openweathermap"
    owm_api_key: str = ""
    owm_base_url: str = "https://api.openweathermap.org/data/2.5/air_pollution"
    fetch_interval_minutes: int = 30
    reading_ttl_minutes: int = 30

    # Ogohlantirishlar
    alert_threshold: int = 150
    alert_clear_threshold: int = 130
    alert_repeat_hours: int = 6
    daily_digest_hour: int = 7
    timezone: str = "Asia/Tashkent"

    # Murojaatlar
    max_complaints_per_day: int = 5
    max_district_distance_km: float = 100.0
    media_dir: str = "./media"

    log_level: str = "INFO"

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}/telegram/webhook"


@lru_cache
def get_settings() -> Settings:
    return Settings()
