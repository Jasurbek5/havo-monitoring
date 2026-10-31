"""Telegram Mini App uchun ma'lumotlar servisi: Havo sifati, ob-havo, soatlik va 7 kunlik prognoz."""

from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
import json
import logging
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.aqi import AQILevel, LEVEL_EMOJI, level_for
from app.core.i18n import t
from app.models import District, DistrictKind
from app.services.air_quality import AirQualityProvider, get_current_reading
from app.services.weather import (
    CurrentWeather,
    WeeklyForecast,
    get_current_weather,
    get_weather_http_client,
    get_weekly_weather,
    get_wmo_info,
    owm_id_to_wmo,
)

log = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

AQI_COLORS = {
    AQILevel.GOOD: "#22c55e",       # Yashil
    AQILevel.MODERATE: "#eab308",   # Sariq
    AQILevel.UNHEALTHY: "#f97316",  # To'q sariq
    AQILevel.DANGEROUS: "#ef4444",  # Qizil
}


def _get_wind_direction(degrees: int | None, lang: str = "uz") -> str:
    if degrees is None:
        return "—"
    directions = {
        "uz": ["Shimoliy (N)", "Shimoli-sharqiy (NE)", "Sharqiy (E)", "Janubi-sharqiy (SE)",
               "Janubiy (S)", "Janubi-g'arbiy (SW)", "G'arbiy (W)", "Shimoli-g'arbiy (NW)"],
        "ru": ["Северный (N)", "Северо-восточный (NE)", "Восточный (E)", "Юго-восточный (SE)",
               "Южный (S)", "Юго-западный (SW)", "Западный (W)", "Северо-западный (NW)"],
        "en": ["North (N)", "North-East (NE)", "East (E)", "South-East (SE)",
               "South (S)", "South-West (SW)", "West (W)", "North-West (NW)"]
    }
    lang_dirs = directions.get(lang, directions["uz"])
    idx = round(degrees / 45) % 8
    return lang_dirs[idx]


async def fetch_hourly_forecast(
    redis: Redis | None,
    lat: float,
    lon: float,
    api_key: str,
    tz_offset_sec: int = 18000,
    ttl_minutes: int = 30,
) -> list[dict[str, Any]]:
    """Keyingi 24 soatlik ob-havo prognozi (Open-Meteo va OWM zaxirasi bilan)."""
    cache_key = f"weather:hourly:{round(lat, 3)}:{round(lon, 3)}"
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    client = get_weather_http_client()
    local_tz = timezone(timedelta(seconds=tz_offset_sec))
    result: list[dict[str, Any]] = []

    # 1. Open-Meteo 1-soatlik prognoz
    try:
        resp = await client.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,weather_code,precipitation_probability",
                "forecast_days": 2,
                "timezone": "auto",
            },
            timeout=4.0,
        )
        if resp.status_code == 200:
            data = resp.json().get("hourly", {})
            times = data.get("time", [])
            temps = data.get("temperature_2m", [])
            codes = data.get("weather_code", [])
            pops = data.get("precipitation_probability", [])

            now_local = datetime.now(local_tz)
            today_date = now_local.date()
            now_iso_prefix = now_local.strftime("%Y-%m-%dT%H")

            start_idx = 0
            for i, t_str in enumerate(times):
                if t_str.startswith(now_iso_prefix) or t_str >= now_local.strftime("%Y-%m-%dT%H:00"):
                    start_idx = i
                    break

            for i in range(start_idx, min(start_idx + 24, len(times))):
                dt = datetime.fromisoformat(times[i])
                wmo = int(codes[i]) if i < len(codes) else 0
                emoji, cond_key = get_wmo_info(wmo)
                result.append({
                    "time": dt.strftime("%H:%M"),
                    "temp": round(float(temps[i]), 1),
                    "emoji": emoji,
                    "condition_key": cond_key,
                    "pop": int(pops[i]) if i < len(pops) and pops[i] is not None else 0,
                    "is_now": (i == start_idx),
                    "is_tomorrow": dt.date() > today_date,
                })
    except Exception as exc:
        log.warning("Open-Meteo hourly xatosi: %r", exc)

    # 2. Agar Open-Meteo ishlamasa, OpenWeatherMap 3-soatlik prognozi
    if not result and api_key:
        try:
            resp = await client.get(
                OWM_FORECAST_URL,
                params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
                timeout=4.0,
            )
            if resp.status_code == 200:
                now_local = datetime.now(local_tz)
                today_date = now_local.date()
                items = resp.json().get("list", [])[:8]
                for idx, it in enumerate(items):
                    dt = datetime.fromtimestamp(it["dt"], tz=local_tz)
                    weather_item = it.get("weather", [{}])[0]
                    wmo = owm_id_to_wmo(weather_item.get("id", 800))
                    emoji, cond_key = get_wmo_info(wmo)
                    result.append({
                        "time": dt.strftime("%H:%M"),
                        "temp": round(float(it["main"]["temp"]), 1),
                        "emoji": emoji,
                        "condition_key": cond_key,
                        "pop": round(float(it.get("pop", 0)) * 100),
                        "is_now": (idx == 0),
                        "is_tomorrow": dt.date() > today_date,
                    })
        except Exception as exc:
            log.warning("OWM hourly xatosi: %r", exc)

    if result and redis is not None:
        try:
            await redis.set(cache_key, json.dumps(result), ex=ttl_minutes * 60)
        except Exception:
            pass

    return result


def _format_day_name(d: datetime, idx: int, lang: str) -> str:
    if idx == 0:
        return "Bugun" if lang == "uz" else ("Сегодня" if lang == "ru" else "Today")
    if idx == 1:
        return "Ertaga" if lang == "uz" else ("Завтра" if lang == "ru" else "Tomorrow")

    weekdays = {
        "uz": ["Dush", "Sesh", "Chor", "Pay", "Juma", "Shan", "Yak"],
        "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }
    return weekdays.get(lang, weekdays["uz"])[d.weekday()]


async def get_miniapp_full_data(
    session: AsyncSession,
    redis: Redis | None,
    provider: AirQualityProvider,
    settings: Settings,
    district: District,
    lang: str = "uz",
) -> dict[str, Any]:
    """Mini App uchun to'liq havo va ob-havo ma'lumotlari to'plami."""
    # 1. Ob-havo (Joriy va haftalik)
    tz_offset = 18000  # Default UTC+5
    weather: CurrentWeather | None = None
    weekly: WeeklyForecast | None = None
    try:
        weather = await get_current_weather(
            redis, district, settings.owm_api_key, ttl_minutes=settings.reading_ttl_minutes
        )
        if weather:
            tz_offset = weather.timezone_offset
    except Exception as exc:
        log.warning("MiniApp: weather olinmadi: %r", exc)

    try:
        weekly = await get_weekly_weather(
            redis, district, settings.owm_api_key, ttl_minutes=settings.reading_ttl_minutes
        )
    except Exception as exc:
        log.warning("MiniApp: weekly olinmadi: %r", exc)

    # 2. Havo sifati (Reading)
    aqi_val = 50
    level = AQILevel.GOOD
    reading_pm25 = None
    reading_pm10 = None
    now_local = datetime.now(timezone(timedelta(seconds=tz_offset)))
    updated_at_str = now_local.strftime("%H:%M")
    try:
        reading = await get_current_reading(
            session, redis, provider, district, ttl_minutes=settings.reading_ttl_minutes
        )
        aqi_val = reading.aqi
        level = level_for(aqi_val)
        reading_pm25 = reading.pm2_5
        reading_pm10 = reading.pm10
        updated_at_str = reading.recorded_at.astimezone(timezone(timedelta(seconds=tz_offset))).strftime("%H:%M")
    except Exception as exc:
        log.warning("MiniApp: havo sifati olinmadi: %r", exc)

    # 3. Soatlik prognoz (24 soat)
    hourly = await fetch_hourly_forecast(
        redis,
        district.lat,
        district.lon,
        settings.owm_api_key,
        tz_offset_sec=tz_offset,
        ttl_minutes=settings.reading_ttl_minutes,
    )

    # Quyosh chiqishi/botishi hisobi
    sunrise_str = "—"
    sunset_str = "—"
    sun_progress = 0.5
    if weather and weather.sunrise and weather.sunset:
        local_tz = timezone(timedelta(seconds=weather.timezone_offset))
        sunrise_local = weather.sunrise.astimezone(local_tz)
        sunset_local = weather.sunset.astimezone(local_tz)
        sunrise_str = sunrise_local.strftime("%H:%M")
        sunset_str = sunset_local.strftime("%H:%M")
        now_local = datetime.now(local_tz)
        if now_local < sunrise_local:
            sun_progress = 0.0
        elif now_local > sunset_local:
            sun_progress = 1.0
        else:
            total_sec = max(1.0, (sunset_local - sunrise_local).total_seconds())
            curr_sec = (now_local - sunrise_local).total_seconds()
            sun_progress = max(0.0, min(1.0, round(curr_sec / total_sec, 2)))

    # 4. Haftalik prognozni formatlash
    weekly_formatted = []
    if weekly and weekly.days:
        for idx, day in enumerate(weekly.days):
            dt = datetime.fromisoformat(day.date_str)
            day_title = _format_day_name(dt, idx, lang)
            condition_text = t(lang, day.condition_key)
            weekly_formatted.append({
                "date": day.date_str,
                "day_name": day_title,
                "temp_min": day.temp_min,
                "temp_max": day.temp_max,
                "emoji": day.emoji,
                "condition": condition_text,
                "pop": day.precipitation_prob or 0,
            })

    # UV indeksini baholash (soat va faslga qarab, agar API bermasa)
    uv_val = 3
    uv_cat = "O'rtacha" if lang == "uz" else ("Умеренный" if lang == "ru" else "Moderate")
    now_hour = datetime.now(timezone(timedelta(seconds=tz_offset))).hour
    if now_hour < 7 or now_hour > 19:
        uv_val = 0
        uv_cat = "Past (0)" if lang == "uz" else ("Низкий (0)" if lang == "ru" else "Low (0)")
    elif 11 <= now_hour <= 15:
        uv_val = 5
        uv_cat = "Yuqori (5)" if lang == "uz" else ("Высокий (5)" if lang == "ru" else "High (5)")

    # Ob-havo holati matni (til bo'yicha to'g'ri tarjima)
    emoji, cond_key = get_wmo_info(weather.weather_code if weather else 0)
    if lang == "en" and weather and weather.description:
        cond_name = weather.description.capitalize()
    else:
        cond_name = t(lang, cond_key)

    return {
        "district": {
            "id": district.id,
            "name": district.name(lang),
            "name_uz": district.name_uz,
            "name_ru": district.name_ru,
            "name_en": district.name_en or district.name_uz,
            "lat": district.lat,
            "lon": district.lon,
            "is_city": district.kind == DistrictKind.CITY_DISTRICT,
        },
        "air": {
            "aqi": aqi_val,
            "level": level.value,
            "level_name": t(lang, f"level_{level.value}"),
            "emoji": LEVEL_EMOJI[level],
            "color": AQI_COLORS[level],
            "pm2_5": reading_pm25,
            "pm10": reading_pm10,
            "advice": t(lang, f"advice_{level.value}"),
            "updated_at": updated_at_str,
        },
        "weather": {
            "temp": weather.temp if weather else 20.0,
            "feels_like": weather.feels_like if weather else 20.0,
            "temp_min": weather.temp_min if weather else 15.0,
            "temp_max": weather.temp_max if weather else 25.0,
            "condition": cond_name,
            "emoji": weather.emoji if weather else "☀️",
            "weather_code": weather.weather_code if weather else 0,
            "humidity": weather.humidity if weather else 45,
            "pressure_hpa": weather.pressure_hpa if weather else 1013,
            "pressure_mmhg": weather.pressure_mmhg if weather else 760,
            "wind_speed": weather.wind_speed if weather else 2.5,
            "wind_deg": weather.wind_deg if weather else 0,
            "wind_dir": _get_wind_direction(weather.wind_deg if weather else None, lang),
            "uv_index": uv_val,
            "uv_category": uv_cat,
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "sun_progress": sun_progress,
        },
        "hourly": hourly,
        "weekly": weekly_formatted,
    }
