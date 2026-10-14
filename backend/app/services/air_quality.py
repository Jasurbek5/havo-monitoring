"""Havo sifati ma'lumotini olish: provayder, saqlash va keshlash."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.aqi import calc_aqi
from app.models import AirQualityLog, District

log = logging.getLogger(__name__)


class ProviderError(Exception):
    """Provayderdan ma'lumot olib bo'lmadi (tarmoq, kalit, noto'g'ri javob)."""


@dataclass(frozen=True, slots=True)
class AirReading:
    """Provayderdan kelgan bitta o'lchov (provayderdan mustaqil format)."""

    aqi: int
    pm2_5: float | None
    pm10: float | None
    recorded_at: datetime  # UTC, tz-aware
    source: str


class AirQualityProvider(Protocol):
    name: str

    async def fetch(self, lat: float, lon: float) -> AirReading: ...

    async def aclose(self) -> None: ...


class OpenWeatherMapProvider:
    """OpenWeatherMap Air Pollution API (koordinata bo'yicha).

    OWM o'zining 1-5 shkalasini ham qaytaradi, lekin biz uni ishlatmaymiz: PM2.5 va PM10
    konsentratsiyasidan standart AQI (0-500) hisoblaymiz.
    """

    name = "openweathermap"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openweathermap.org/data/2.5/air_pollution",
        *,
        client: httpx.AsyncClient | None = None,
        retries: int = 3,
        backoff: float = 0.5,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._url = base_url
        self._retries = max(1, retries)
        self._backoff = backoff
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def fetch(self, lat: float, lon: float) -> AirReading:
        if not self._api_key:
            raise ProviderError("OWM_API_KEY sozlanmagan")
        params = {"lat": lat, "lon": lon, "appid": self._api_key}

        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = await self._client.get(self._url, params=params)
            except httpx.HTTPError as exc:  # tarmoq xatosi yoki timeout: qayta urinamiz
                last_error = exc
            else:
                status = response.status_code
                if status in (401, 403):
                    raise ProviderError(f"API kalit rad etildi (HTTP {status})")
                if status == 429 or status >= 500:
                    last_error = ProviderError(f"HTTP {status}")
                elif status >= 400:
                    raise ProviderError(f"Provayder xatosi (HTTP {status})")
                else:
                    return self._parse(response)
            if attempt < self._retries:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        raise ProviderError(f"Provayder javob bermadi: {last_error}") from last_error

    def _parse(self, response: httpx.Response) -> AirReading:
        try:
            item = response.json()["list"][0]
            components = item["components"]
            pm2_5 = components.get("pm2_5")
            pm10 = components.get("pm10")
            return AirReading(
                aqi=calc_aqi(pm2_5, pm10),
                pm2_5=None if pm2_5 is None else float(pm2_5),
                pm10=None if pm10 is None else float(pm10),
                recorded_at=datetime.fromtimestamp(int(item["dt"]), tz=UTC),
                source=self.name,
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Provayder javobi tushunarsiz: {exc!r}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def build_provider(settings: Settings) -> AirQualityProvider:
    """Provayderni almashtirish kerak bo'lsa, faqat shu funksiya o'zgaradi."""
    return OpenWeatherMapProvider(settings.owm_api_key, settings.owm_base_url)


async def fetch_air_quality(district: District, provider: AirQualityProvider) -> AirReading:
    """Hududning joriy havo holatini provayderdan oladi (bazaga yozmaydi)."""
    return await provider.fetch(district.lat, district.lon)


# ---------------------------------------------------------------------------
# Saqlash va keshlash
# ---------------------------------------------------------------------------


async def store_reading(
    session: AsyncSession, district_id: int, reading: AirReading
) -> AirQualityLog | None:
    """O'lchovni yozadi. Shu vaqtdagi o'lchov allaqachon bor bo'lsa, None qaytaradi."""
    exists = await session.scalar(
        select(AirQualityLog.id).where(
            AirQualityLog.district_id == district_id,
            AirQualityLog.recorded_at == reading.recorded_at,
        )
    )
    if exists is not None:
        return None
    row = AirQualityLog(
        district_id=district_id,
        aqi=reading.aqi,
        pm2_5=reading.pm2_5,
        pm10=reading.pm10,
        source=reading.source,
        recorded_at=reading.recorded_at,
    )
    try:
        async with session.begin_nested():  # parallel yozuv bo'lsa unique cheklov ushlaydi
            session.add(row)
    except IntegrityError:
        return None
    return row


async def latest_log(session: AsyncSession, district_id: int) -> AirQualityLog | None:
    return await session.scalar(
        select(AirQualityLog)
        .where(AirQualityLog.district_id == district_id)
        .order_by(AirQualityLog.recorded_at.desc())
        .limit(1)
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class CurrentReading:
    """Foydalanuvchiga ko'rsatiladigan joriy holat."""

    aqi: int
    pm2_5: float | None
    pm10: float | None
    recorded_at: datetime
    fetched_at: datetime
    stale: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "aqi": self.aqi,
                "pm2_5": self.pm2_5,
                "pm10": self.pm10,
                "recorded_at": self.recorded_at.isoformat(),
                "fetched_at": self.fetched_at.isoformat(),
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "CurrentReading":
        data = json.loads(raw)
        return cls(
            aqi=int(data["aqi"]),
            pm2_5=data["pm2_5"],
            pm10=data["pm10"],
            recorded_at=_aware(datetime.fromisoformat(data["recorded_at"])),
            fetched_at=_aware(datetime.fromisoformat(data["fetched_at"])),
        )

    @classmethod
    def from_log(cls, row: AirQualityLog, *, stale: bool = False) -> "CurrentReading":
        return cls(
            aqi=row.aqi,
            pm2_5=row.pm2_5,
            pm10=row.pm10,
            recorded_at=_aware(row.recorded_at),
            fetched_at=_aware(row.created_at),
            stale=stale,
        )


def _cache_key(district_id: int) -> str:
    return f"aq:current:{district_id}"


async def _cache_get(redis: Redis | None, district_id: int) -> CurrentReading | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(_cache_key(district_id))
        return CurrentReading.from_json(raw) if raw else None
    except (RedisError, ValueError, KeyError, TypeError) as exc:
        log.warning("Kesh o'qishda xato: %r", exc)
        return None


async def _cache_set(redis: Redis | None, district_id: int, reading: CurrentReading, ttl: int) -> None:
    if redis is None:
        return
    try:
        await redis.set(_cache_key(district_id), reading.to_json(), ex=ttl)
    except RedisError as exc:
        log.warning("Kesh yozishda xato: %r", exc)


async def cache_reading(
    redis: Redis | None,
    district_id: int,
    reading: AirReading,
    *,
    ttl_minutes: int,
    now: datetime | None = None,
) -> None:
    """Yangi o'lchovni keshga qo'yadi (Celery yangilagach bot eski qiymat ko'rsatmasligi uchun)."""
    current = CurrentReading(
        aqi=reading.aqi,
        pm2_5=reading.pm2_5,
        pm10=reading.pm10,
        recorded_at=reading.recorded_at,
        fetched_at=now or datetime.now(UTC),
    )
    await _cache_set(redis, district_id, current, ttl_minutes * 60)


async def get_current_reading(
    session: AsyncSession,
    redis: Redis | None,
    provider: AirQualityProvider,
    district: District,
    *,
    ttl_minutes: int = 30,
    now: datetime | None = None,
) -> CurrentReading:
    """Hudud uchun joriy holat: kesh -> bazadagi yangi o'lchov -> provayder.

    Toshkent tumanlari Celery orqali oldindan yangilanadi, shuning uchun odatda baza yoki
    keshdan javob beriladi. Viloyatlar uchun ma'lumot birinchi so'rovda olinib, `ttl_minutes`
    davomida keshlanadi. Provayder ishlamasa va eski o'lchov bo'lsa, `stale=True` bilan
    shu eski o'lchov qaytariladi; hech narsa bo'lmasa ProviderError ko'tariladi.
    """
    now = now or datetime.now(UTC)
    ttl = timedelta(minutes=ttl_minutes)

    cached = await _cache_get(redis, district.id)
    if cached is not None:
        return cached

    latest = await latest_log(session, district.id)
    if latest is not None and now - _aware(latest.created_at) < ttl:
        reading = CurrentReading.from_log(latest)
        await _cache_set(redis, district.id, reading, int(ttl.total_seconds()))
        return reading

    try:
        fresh = await fetch_air_quality(district, provider)
    except ProviderError:
        if latest is None:
            raise
        log.warning("Provayder ishlamadi, %s uchun eski o'lchov ko'rsatiladi", district.slug)
        return CurrentReading.from_log(latest, stale=True)

    await store_reading(session, district.id, fresh)
    reading = CurrentReading(
        aqi=fresh.aqi,
        pm2_5=fresh.pm2_5,
        pm10=fresh.pm10,
        recorded_at=fresh.recorded_at,
        fetched_at=now,
    )
    await _cache_set(redis, district.id, reading, int(ttl.total_seconds()))
    return reading
