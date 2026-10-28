"""Ob-havo servisi, formatlash va kesh testlari."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
import pytest

from app.core.locales import en, ru, uz
from app.core.messages import (
    format_air_message,
    format_digest_message,
    format_full_weather_message,
    format_weekly_forecast_message,
    smart_weather_tip,
    wind_direction_label,
)
from app.core.memory_cache import MemoryCache
from app.models import District
from app.services.weather import (
    CurrentWeather,
    DailyForecast,
    WeeklyForecast,
    get_current_weather,
    get_weekly_weather,
    get_wmo_info,
    owm_id_to_wmo,
)

TZ = ZoneInfo("Asia/Tashkent")
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _sample_weather() -> CurrentWeather:
    return CurrentWeather(
        temp=22.4,
        feels_like=21.0,
        temp_min=14.0,
        temp_max=24.5,
        humidity=48,
        pressure_hpa=1014,
        wind_speed=3.6,
        wind_deg=10,
        weather_code=0,
        description="Clear sky",
        emoji="☀️",
        sunrise=datetime(2026, 10, 28, 2, 30, tzinfo=UTC),
        sunset=datetime(2026, 10, 28, 13, 15, tzinfo=UTC),
        recorded_at=NOW,
    )


def _sample_weekly() -> WeeklyForecast:
    days = [
        DailyForecast(
            date_str="2026-10-28",
            weather_code=0,
            emoji="☀️",
            condition_key="weather_clear",
            temp_max=24.0,
            temp_min=12.0,
            wind_speed_max=4.0,
            precipitation_prob=0,
        ),
        DailyForecast(
            date_str="2026-10-29",
            weather_code=61,
            emoji="🌧",
            condition_key="weather_slight_rain",
            temp_max=18.0,
            temp_min=9.0,
            wind_speed_max=6.5,
            precipitation_prob=75,
        ),
    ]
    return WeeklyForecast(days=days, fetched_at=NOW)


def test_wmo_codes_and_owm_mapping():
    emoji, key = get_wmo_info(0)
    assert emoji == "☀️" and key == "weather_clear"

    emoji, key = get_wmo_info(61)
    assert emoji == "🌧" and key == "weather_slight_rain"

    assert owm_id_to_wmo(800) == 0  # clear
    assert owm_id_to_wmo(500) == 61  # rain
    assert owm_id_to_wmo(200) == 95  # thunderstorm


def test_wind_directions():
    assert wind_direction_label("uz", 0) == "Shimoliy"
    assert wind_direction_label("ru", 90) == "Восточный"
    assert wind_direction_label("en", 180) == "South"
    assert wind_direction_label("uz", 270) == "G'arbiy"
    assert wind_direction_label("uz", None) == "—"


def test_smart_weather_tips():
    rain_weather = CurrentWeather(
        temp=15.0,
        feels_like=14.0,
        temp_min=10.0,
        temp_max=17.0,
        humidity=80,
        pressure_hpa=1010,
        wind_speed=5.0,
        wind_deg=180,
        weather_code=61,
        description="Rain",
        emoji="🌧",
        sunrise=None,
        sunset=None,
        recorded_at=NOW,
    )
    assert "soyabon" in smart_weather_tip("uz", rain_weather).lower()
    assert "зонт" in smart_weather_tip("ru", rain_weather).lower()
    assert "umbrella" in smart_weather_tip("en", rain_weather).lower()


def test_current_weather_json_serialization():
    w = _sample_weather()
    raw = w.to_json()
    loaded = CurrentWeather.from_json(raw)
    assert loaded.temp == w.temp
    assert loaded.feels_like == w.feels_like
    assert loaded.pressure_mmhg == round(1014 * 0.750062)
    assert loaded.recorded_at == w.recorded_at


def test_weekly_forecast_json_serialization():
    wf = _sample_weekly()
    raw = wf.to_json()
    loaded = WeeklyForecast.from_json(raw)
    assert len(loaded.days) == 2
    assert loaded.days[0].temp_max == 24.0
    assert loaded.days[1].precipitation_prob == 75


def test_combined_air_weather_message():
    weather = _sample_weather()
    text = format_air_message(
        "uz",
        "Chilonzor",
        aqi=42,
        pm2_5=8.5,
        pm10=18.0,
        recorded_at=NOW,
        tz=TZ,
        weather=weather,
    )
    assert "Chilonzor" in text
    assert "+22.4°C" in text
    assert "42" in text
    assert "☀️" in text
    assert "Ochiq havo" in text


def test_full_weather_message():
    weather = _sample_weather()
    text = format_full_weather_message("uz", "Chilonzor", weather, tz=TZ)
    assert "Chilonzor" in text
    assert "+22.4°C" in text
    assert "Quyosh chiqishi" in text
    assert "761 mm sim. ust." in text


def test_weekly_forecast_message():
    weekly = _sample_weekly()
    text = format_weekly_forecast_message("uz", "Chilonzor", weekly, tz=TZ)
    assert "7 kunlik" in text
    assert "Chilonzor" in text
    assert "☀️" in text
    assert "+24° / +12°" in text
    assert "🌧 75%" in text


def test_digest_message_with_weather():
    weather = _sample_weather()
    text = format_digest_message("uz", "Chilonzor", aqi=35, weather=weather)
    assert "Xayrli tong!" in text
    assert "35" in text
    assert "+22.4°C" in text


@pytest.mark.asyncio
async def test_weather_cache_memory():
    cache = MemoryCache()
    district = District(
        id=99,
        slug="test-dist",
        name_uz="Test",
        name_ru="Тест",
        lat=41.3,
        lon=69.2,
        alert_active=False,
    )
    weather = _sample_weather()
    # Keshga qo'lda yozamiz
    await cache.set(f"weather:current:{district.id}", weather.to_json(), ex=60)

    # get_current_weather keshdan olishi kerak (hech qanday HTTP chaqiruvsiz)
    cached = await get_current_weather(cache, district, owm_api_key="")
    assert cached.temp == weather.temp
    assert cached.humidity == weather.humidity


def test_location_result_display_name():
    from app.services.geocoding import LocationResult

    loc = LocationResult(
        name_uz="Urgut",
        name_ru="Ургут",
        name_en="Urgut",
        lat=39.4,
        lon=67.24,
        country="Uzbekistan",
        admin_area="Samarqand viloyati",
    )
    assert loc.display_name("uz") == "Urgut, Samarqand viloyati"
    assert loc.display_name("ru") == "Ургут, Samarqand viloyati"

    foreign_loc = LocationResult(
        name_uz="Almati",
        name_ru="Алматы",
        name_en="Almaty",
        lat=43.25,
        lon=76.95,
        country="Kazakhstan",
        admin_area="Almaty",
    )
    assert "Kazakhstan" in foreign_loc.display_name("en")
    assert "Almati" in foreign_loc.display_name("uz")
