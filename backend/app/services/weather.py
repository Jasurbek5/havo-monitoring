"""Ob-havo ma'lumotlarini olish va keshlash (Joriy va haftalik prognoz).

Manbalar:
1. Joriy ob-havo: OpenWeatherMap (zaxira: Open-Meteo).
2. Haftalik prognoz: Open-Meteo 7 kunlik (zaxira: OpenWeatherMap 5 kunlik).
"""

import asyncio
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import json
import logging
from typing import Any

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.models import District

log = logging.getLogger(__name__)

OWM_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Tezkor ishlash uchun Keep-Alive ulanishlar puli (har safar yangi client ochib-yopilmaydi)
_shared_client: httpx.AsyncClient | None = None


def get_weather_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=5.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _shared_client


class WeatherError(Exception):
    """Ob-havo ma'lumotini olib bo'lmadi."""


# WMO ob-havo kodlari va emojilar
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("☀️", "weather_clear"),
    1: ("🌤", "weather_mostly_clear"),
    2: ("⛅", "weather_partly_cloudy"),
    3: ("☁️", "weather_cloudy"),
    45: ("🌫", "weather_fog"),
    48: ("🌫", "weather_depositing_rime_fog"),
    51: ("🌦", "weather_light_drizzle"),
    53: ("🌦", "weather_moderate_drizzle"),
    55: ("🌧", "weather_dense_drizzle"),
    61: ("🌧", "weather_slight_rain"),
    63: ("🌧", "weather_moderate_rain"),
    65: ("🌧", "weather_heavy_rain"),
    71: ("🌨", "weather_slight_snow"),
    73: ("🌨", "weather_moderate_snow"),
    75: ("❄️", "weather_heavy_snow"),
    77: ("❄️", "weather_snow_grains"),
    80: ("🌦", "weather_slight_showers"),
    81: ("🌧", "weather_moderate_showers"),
    82: ("⛈", "weather_violent_showers"),
    85: ("🌨", "weather_snow_showers"),
    86: ("❄️", "weather_heavy_snow_showers"),
    95: ("⛈", "weather_thunderstorm"),
    96: ("⛈", "weather_thunderstorm_slight_hail"),
    99: ("⛈", "weather_thunderstorm_heavy_hail"),
}


def get_wmo_info(code: int) -> tuple[str, str]:
    return WMO_CODES.get(code, ("🌤", "weather_partly_cloudy"))


def owm_id_to_wmo(weather_id: int) -> int:
    if 200 <= weather_id < 300:
        return 95
    if 300 <= weather_id < 400:
        return 51
    if 500 <= weather_id < 510:
        return 61
    if weather_id == 511:
        return 66
    if 520 <= weather_id < 600:
        return 80
    if 600 <= weather_id < 700:
        return 71
    if 700 <= weather_id < 800:
        return 45
    if weather_id == 800:
        return 0
    if weather_id == 801:
        return 1
    if weather_id == 802:
        return 2
    if weather_id in (803, 804):
        return 3
    return 1


@dataclass(frozen=True, slots=True)
class CurrentWeather:
    temp: float
    feels_like: float
    temp_min: float
    temp_max: float
    humidity: int
    pressure_hpa: int
    wind_speed: float
    wind_deg: int | None
    weather_code: int
    description: str
    emoji: str
    sunrise: datetime | None
    sunset: datetime | None
    recorded_at: datetime

    @property
    def pressure_mmhg(self) -> int:
        return round(self.pressure_hpa * 0.750062)

    def to_json(self) -> str:
        data: dict[str, Any] = {
            "temp": self.temp,
            "feels_like": self.feels_like,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "humidity": self.humidity,
            "pressure_hpa": self.pressure_hpa,
            "wind_speed": self.wind_speed,
            "wind_deg": self.wind_deg,
            "weather_code": self.weather_code,
            "description": self.description,
            "emoji": self.emoji,
            "sunrise": self.sunrise.isoformat() if self.sunrise else None,
            "sunset": self.sunset.isoformat() if self.sunset else None,
            "recorded_at": self.recorded_at.isoformat(),
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str) -> "CurrentWeather":
        d = json.loads(raw)
        sunrise = datetime.fromisoformat(d["sunrise"]) if d.get("sunrise") else None
        sunset = datetime.fromisoformat(d["sunset"]) if d.get("sunset") else None
        recorded_at = datetime.fromisoformat(d["recorded_at"])
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)
        return cls(
            temp=float(d["temp"]),
            feels_like=float(d["feels_like"]),
            temp_min=float(d["temp_min"]),
            temp_max=float(d["temp_max"]),
            humidity=int(d["humidity"]),
            pressure_hpa=int(d["pressure_hpa"]),
            wind_speed=float(d["wind_speed"]),
            wind_deg=d.get("wind_deg"),
            weather_code=int(d["weather_code"]),
            description=d["description"],
            emoji=d["emoji"],
            sunrise=sunrise,
            sunset=sunset,
            recorded_at=recorded_at,
        )


@dataclass(frozen=True, slots=True)
class DailyForecast:
    date_str: str  # YYYY-MM-DD
    weather_code: int
    emoji: str
    condition_key: str
    temp_max: float
    temp_min: float
    wind_speed_max: float
    precipitation_prob: int | None

    @property
    def parsed_date(self) -> date:
        return date.fromisoformat(self.date_str)


@dataclass(frozen=True, slots=True)
class WeeklyForecast:
    days: list[DailyForecast]
    fetched_at: datetime

    def to_json(self) -> str:
        data = {
            "days": [asdict(d) for d in self.days],
            "fetched_at": self.fetched_at.isoformat(),
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str) -> "WeeklyForecast":
        d = json.loads(raw)
        fetched_at = datetime.fromisoformat(d["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        days = [DailyForecast(**item) for item in d["days"]]
        return cls(days=days, fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# API chaqiruvlari (Tezkor va xatolikka chidamli)
# ---------------------------------------------------------------------------


async def fetch_current_weather_owm(
    lat: float, lon: float, api_key: str, *, client: httpx.AsyncClient | None = None
) -> CurrentWeather:
    """OpenWeatherMap orqali joriy ob-havo."""
    c = client or get_weather_http_client()
    resp = await c.get(
        OWM_WEATHER_URL,
        params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
    )
    if resp.status_code != 200:
        raise WeatherError(f"OWM weather xatosi: HTTP {resp.status_code}")
    data = resp.json()
    main = data["main"]
    wind = data.get("wind", {})
    weather_item = data.get("weather", [{}])[0]
    weather_id = weather_item.get("id", 800)
    description = weather_item.get("description", "")
    sys_data = data.get("sys", {})

    wmo = owm_id_to_wmo(weather_id)
    emoji, _ = get_wmo_info(wmo)

    sunrise = (
        datetime.fromtimestamp(sys_data["sunrise"], tz=UTC)
        if "sunrise" in sys_data
        else None
    )
    sunset = (
        datetime.fromtimestamp(sys_data["sunset"], tz=UTC)
        if "sunset" in sys_data
        else None
    )

    return CurrentWeather(
        temp=round(float(main["temp"]), 1),
        feels_like=round(float(main.get("feels_like", main["temp"])), 1),
        temp_min=round(float(main.get("temp_min", main["temp"])), 1),
        temp_max=round(float(main.get("temp_max", main["temp"])), 1),
        humidity=int(main.get("humidity", 0)),
        pressure_hpa=int(main.get("pressure", 1013)),
        wind_speed=round(float(wind.get("speed", 0.0)), 1),
        wind_deg=wind.get("deg"),
        weather_code=wmo,
        description=description,
        emoji=emoji,
        sunrise=sunrise,
        sunset=sunset,
        recorded_at=datetime.fromtimestamp(data.get("dt", int(datetime.now(UTC).timestamp())), tz=UTC),
    )


async def fetch_current_weather_open_meteo(
    lat: float, lon: float, *, client: httpx.AsyncClient | None = None
) -> CurrentWeather:
    """Zaxira: Open-Meteo orqali joriy ob-havo."""
    c = client or get_weather_http_client()
    resp = await c.get(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,wind_speed_10m,wind_direction_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "timezone": "auto",
        },
    )
    if resp.status_code != 200:
        raise WeatherError(f"Open-Meteo current xatosi: HTTP {resp.status_code}")
    data = resp.json()
    current = data["current"]
    daily = data.get("daily", {})

    wmo = int(current.get("weather_code", 0))
    emoji, _ = get_wmo_info(wmo)

    temp_max = daily.get("temperature_2m_max", [current["temperature_2m"]])[0]
    temp_min = daily.get("temperature_2m_min", [current["temperature_2m"]])[0]

    sunrise = None
    sunset = None
    if daily.get("sunrise"):
        try:
            sunrise = datetime.fromisoformat(daily["sunrise"][0]).replace(tzinfo=UTC)
        except Exception:
            pass
    if daily.get("sunset"):
        try:
            sunset = datetime.fromisoformat(daily["sunset"][0]).replace(tzinfo=UTC)
        except Exception:
            pass

    return CurrentWeather(
        temp=round(float(current["temperature_2m"]), 1),
        feels_like=round(float(current.get("apparent_temperature", current["temperature_2m"])), 1),
        temp_min=round(float(temp_min), 1),
        temp_max=round(float(temp_max), 1),
        humidity=int(current.get("relative_humidity_2m", 0)),
        pressure_hpa=round(float(current.get("surface_pressure", 1013))),
        wind_speed=round(float(current.get("wind_speed_10m", 0.0)), 1),
        wind_deg=int(current.get("wind_direction_10m", 0)),
        weather_code=wmo,
        description="",
        emoji=emoji,
        sunrise=sunrise,
        sunset=sunset,
        recorded_at=datetime.now(UTC),
    )


async def fetch_weekly_forecast_open_meteo(
    lat: float, lon: float, *, client: httpx.AsyncClient | None = None
) -> WeeklyForecast:
    """Open-Meteo orqali 7 kunlik ob-havo prognozi."""
    c = client or get_weather_http_client()
    resp = await c.get(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,precipitation_probability_max",
            "timezone": "auto",
        },
    )
    if resp.status_code != 200:
        raise WeatherError(f"Open-Meteo weekly xatosi: HTTP {resp.status_code}")
    data = resp.json()["daily"]
    dates = data["time"]
    codes = data["weather_code"]
    max_temps = data["temperature_2m_max"]
    min_temps = data["temperature_2m_min"]
    winds = data.get("wind_speed_10m_max", [0.0] * len(dates))
    precip_probs = data.get("precipitation_probability_max", [None] * len(dates))

    days: list[DailyForecast] = []
    for i in range(min(7, len(dates))):
        wmo = int(codes[i])
        emoji, key = get_wmo_info(wmo)
        days.append(
            DailyForecast(
                date_str=dates[i],
                weather_code=wmo,
                emoji=emoji,
                condition_key=key,
                temp_max=round(float(max_temps[i]), 1),
                temp_min=round(float(min_temps[i]), 1),
                wind_speed_max=round(float(winds[i]), 1),
                precipitation_prob=int(precip_probs[i]) if precip_probs[i] is not None else None,
            )
        )
    return WeeklyForecast(days=days, fetched_at=datetime.now(UTC))


async def fetch_weekly_forecast_owm(
    lat: float, lon: float, api_key: str, *, client: httpx.AsyncClient | None = None
) -> WeeklyForecast:
    """Zaxira: OpenWeatherMap 5 kunlik prognozi (har 3 soatlik o'lchovlarni kunlarga birlashtiradi)."""
    c = client or get_weather_http_client()
    resp = await c.get(
        OWM_FORECAST_URL,
        params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
    )
    if resp.status_code != 200:
        raise WeatherError(f"OWM forecast xatosi: HTTP {resp.status_code}")
    items = resp.json().get("list", [])
    if not items:
        raise WeatherError("OWM ro'yxati bo'sh")

    by_day: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        day_str = it["dt_txt"].split(" ")[0]
        by_day[day_str].append(it)

    days: list[DailyForecast] = []
    for day_str, points in by_day.items():
        temps = [p["main"]["temp"] for p in points]
        winds = [p.get("wind", {}).get("speed", 0.0) for p in points]
        pops = [int(p.get("pop", 0) * 100) for p in points]
        # Kunduzgi ob-havoni asosiy qilib olamiz (soat 12:00 yoki o'rtadagi nuqta)
        mid_point = points[len(points) // 2]
        weather_id = mid_point.get("weather", [{}])[0].get("id", 800)
        wmo = owm_id_to_wmo(weather_id)
        emoji, key = get_wmo_info(wmo)

        days.append(
            DailyForecast(
                date_str=day_str,
                weather_code=wmo,
                emoji=emoji,
                condition_key=key,
                temp_max=round(float(max(temps)), 1),
                temp_min=round(float(min(temps)), 1),
                wind_speed_max=round(float(max(winds)), 1),
                precipitation_prob=max(pops) if any(pops) else None,
            )
        )
        if len(days) >= 7:
            break

    return WeeklyForecast(days=days, fetched_at=datetime.now(UTC))


# ---------------------------------------------------------------------------
# Keshlash va servis metodlari
# ---------------------------------------------------------------------------


def _weather_cache_key(district_id: int) -> str:
    return f"weather:current:{district_id}"


def _weekly_cache_key(district_id: int) -> str:
    return f"weather:weekly:{district_id}"


async def get_current_weather(
    redis: Redis | None,
    district: District,
    owm_api_key: str = "",
    *,
    ttl_minutes: int = 30,
) -> CurrentWeather:
    """Hudud uchun joriy ob-havoni olish (kesh -> OWM -> Open-Meteo)."""
    # 1. Keshdan tekshirish
    if redis is not None:
        try:
            cached = await redis.get(_weather_cache_key(district.id))
            if cached:
                return CurrentWeather.from_json(cached)
        except (RedisError, ValueError, KeyError) as exc:
            log.warning("Ob-havo keshi o'qishda xato: %r", exc)

    # 2. Provayderdan olish
    weather: CurrentWeather | None = None
    if owm_api_key:
        try:
            weather = await fetch_current_weather_owm(district.lat, district.lon, owm_api_key)
        except Exception as exc:
            log.warning("OWM ob-havo olinmadi: %r. Open-Meteo sinab ko'riladi.", exc)

    if weather is None:
        try:
            weather = await fetch_current_weather_open_meteo(district.lat, district.lon)
        except Exception as exc:
            log.error("Open-Meteo orqali ham ob-havo olinmadi: %r", exc)
            raise WeatherError("Ob-havo ma'lumotini olish imkoni bo'lmadi") from exc

    # 3. Keshga yozish
    if redis is not None and weather is not None:
        try:
            await redis.set(_weather_cache_key(district.id), weather.to_json(), ex=ttl_minutes * 60)
        except RedisError as exc:
            log.warning("Ob-havo keshga yozishda xato: %r", exc)

    return weather


async def get_weekly_weather(
    redis: Redis | None,
    district: District,
    owm_api_key: str = "",
    *,
    ttl_minutes: int = 120,
) -> WeeklyForecast:
    """Hudud uchun haftalik prognoz (kesh -> Open-Meteo -> OWM 5 kunlik zaxira)."""
    # 1. Keshdan tekshirish
    if redis is not None:
        try:
            cached = await redis.get(_weekly_cache_key(district.id))
            if cached:
                return WeeklyForecast.from_json(cached)
        except (RedisError, ValueError, KeyError) as exc:
            log.warning("Haftalik ob-havo keshini o'qishda xato: %r", exc)

    # 2. Open-Meteo orqali olishga urinish
    weekly: WeeklyForecast | None = None
    try:
        weekly = await fetch_weekly_forecast_open_meteo(district.lat, district.lon)
    except Exception as exc:
        log.warning("Open-Meteo haftalik prognoz bermadi: %r. OWM sinab ko'riladi.", exc)

    # 3. Agar Open-Meteo ishlamasa, OWM 5 kunlik prognoziga zaxira
    if weekly is None and owm_api_key:
        try:
            weekly = await fetch_weekly_forecast_owm(district.lat, district.lon, owm_api_key)
        except Exception as exc:
            log.error("OWM orqali ham haftalik prognoz olinmadi: %r", exc)

    if weekly is None:
        raise WeatherError("Haftalik ob-havo ma'lumotini olish imkoni bo'lmadi")

    # 4. Keshga yozish
    if redis is not None and weekly is not None:
        try:
            await redis.set(_weekly_cache_key(district.id), weekly.to_json(), ex=ttl_minutes * 60)
        except RedisError as exc:
            log.warning("Haftalik ob-havoni keshga yozishda xato: %r", exc)

    return weekly
