"""Foydalanuvchiga boradigan xabar matnlarini yig'ish (bot ham, Celery ham shuni ishlatadi)."""

from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

from app.core.aqi import LEVEL_EMOJI, AQILevel, level_for
from app.core.i18n import t
from app.services.weather import CurrentWeather, WeeklyForecast, get_wmo_info


def resolve_effective_tz(
    user_tz: str | None,
    weather: CurrentWeather | None,
    default_tz: ZoneInfo,
) -> tuple[tzinfo, str]:
    """Qaytaradi: (tz, tz_label).

    1. Agar user_tz mavjud bo'lsa va 'auto' bo'lmasa -> ZoneInfo(user_tz).
    2. Aks holda, agar weather ob'ektida timezone_offset bo'lsa -> weather.tz (masalan Tokio UTC+9).
    3. Aks holda -> default_tz (masalan Asia/Tashkent UTC+5).
    """
    if user_tz and user_tz != "auto":
        try:
            return ZoneInfo(user_tz), user_tz
        except Exception:
            pass

    if weather is not None and hasattr(weather, "tz"):
        return weather.tz, weather.tz_name

    return default_tz, "UTC+5"


def _value(number: float | None) -> str:
    return "—" if number is None else f"{number:.1f}"


def advice_for(lang: str, level: AQILevel) -> str:
    return t(lang, f"advice_{level.value}")


def level_label(lang: str, level: AQILevel) -> str:
    return t(lang, f"level_{level.value}")


def wind_direction_label(lang: str, deg: int | None) -> str:
    if deg is None:
        return "—"
    deg = deg % 360
    if deg >= 337.5 or deg < 22.5:
        return t(lang, "wind_n")
    if 22.5 <= deg < 67.5:
        return t(lang, "wind_ne")
    if 67.5 <= deg < 112.5:
        return t(lang, "wind_e")
    if 112.5 <= deg < 157.5:
        return t(lang, "wind_se")
    if 157.5 <= deg < 202.5:
        return t(lang, "wind_s")
    if 202.5 <= deg < 247.5:
        return t(lang, "wind_sw")
    if 247.5 <= deg < 292.5:
        return t(lang, "wind_w")
    return t(lang, "wind_nw")


def weather_condition_label(lang: str, code: int) -> str:
    _, key = get_wmo_info(code)
    return t(lang, key)


def smart_weather_tip(lang: str, weather: CurrentWeather) -> str:
    code = weather.weather_code
    if code in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99):
        return t(lang, "weather_tip_rain")
    if code in (71, 73, 75, 77, 85, 86):
        return t(lang, "weather_tip_snow")
    if weather.temp < 8.0:
        return t(lang, "weather_tip_cold")
    if weather.temp > 32.0:
        return t(lang, "weather_tip_hot")
    return t(lang, "weather_tip_pleasant")


def format_air_message(
    lang: str,
    district_name: str,
    *,
    aqi: int,
    pm2_5: float | None,
    pm10: float | None,
    recorded_at: datetime,
    tz: tzinfo | ZoneInfo,
    tz_label: str = "",
    stale: bool = False,
    weather: CurrentWeather | None = None,
) -> str:
    """Umumiy xabar: havo sifati va (mavjud bo'lsa) ob-havo qisqacha."""
    level = level_for(aqi)
    time_str = recorded_at.astimezone(tz).strftime("%H:%M")
    if tz_label:
        time_str = f"{time_str} ({tz_label})"
    if weather is not None:
        weather_desc = weather_condition_label(lang, weather.weather_code)
        text = t(
            lang,
            "air_weather_message",
            district=district_name,
            weather_emoji=weather.emoji,
            weather_desc=weather_desc,
            temp=f"{weather.temp:+0.1f}".replace("+0.", "0.").replace("-0.", "-0."),
            feels_like=f"{weather.feels_like:+0.1f}",
            humidity=weather.humidity,
            wind=weather.wind_speed,
            emoji=LEVEL_EMOJI[level],
            level=level_label(lang, level),
            aqi=aqi,
            pm25=_value(pm2_5),
            pm10=_value(pm10),
            advice=advice_for(lang, level),
            time=time_str,
        )
    else:
        text = t(
            lang,
            "air_message",
            district=district_name,
            emoji=LEVEL_EMOJI[level],
            level=level_label(lang, level),
            aqi=aqi,
            pm25=_value(pm2_5),
            pm10=_value(pm10),
            time=time_str,
            advice=advice_for(lang, level),
        )
    if stale:
        text += t(lang, "air_stale")
    return text


def format_full_weather_message(
    lang: str,
    district_name: str,
    weather: CurrentWeather,
    *,
    tz: tzinfo | ZoneInfo,
    tz_label: str = "",
) -> str:
    """Bugungi to'liq ob-havo ma'lumoti."""
    weather_desc = weather_condition_label(lang, weather.weather_code)
    wind_dir = wind_direction_label(lang, weather.wind_deg)
    sun_times = ""
    if weather.sunrise and weather.sunset:
        tz_suffix = f" ({tz_label})" if tz_label else ""
        sun_times = t(
            lang,
            "sun_times_format",
            sunrise=weather.sunrise.astimezone(tz).strftime("%H:%M"),
            sunset=weather.sunset.astimezone(tz).strftime("%H:%M"),
            tz=tz_suffix,
        )

    time_str = weather.recorded_at.astimezone(tz).strftime("%H:%M")
    if tz_label:
        time_str = f"{time_str} ({tz_label})"

    return t(
        lang,
        "full_weather_message",
        district=district_name,
        weather_emoji=weather.emoji,
        weather_desc=weather_desc,
        temp=f"{weather.temp:+0.1f}",
        feels_like=f"{weather.feels_like:+0.1f}",
        temp_min=f"{weather.temp_min:+0.1f}",
        temp_max=f"{weather.temp_max:+0.1f}",
        humidity=weather.humidity,
        wind_speed=weather.wind_speed,
        wind_dir=wind_dir,
        pressure_mmhg=weather.pressure_mmhg,
        pressure_hpa=weather.pressure_hpa,
        sun_times=sun_times,
        weather_tip=smart_weather_tip(lang, weather),
        time=time_str,
    )


def _fmt_deg(val: float) -> str:
    r = int(round(val))
    return f"+{r}" if r > 0 else str(r)


def format_weekly_forecast_message(
    lang: str,
    district_name: str,
    weekly: WeeklyForecast,
    *,
    tz: ZoneInfo,
) -> str:
    """7 kunlik ob-havo prognozi."""
    text = t(lang, "weekly_weather_header", district=district_name)
    today = datetime.now(tz).date()

    for item in weekly.days:
        item_date = item.parsed_date
        diff = (item_date - today).days

        if diff == 0:
            day_name = t(lang, "day_today")
        elif diff == 1:
            day_name = t(lang, "day_tomorrow")
        else:
            day_name = t(lang, f"weekday_{item_date.weekday()}")

        formatted_date = item_date.strftime("%d.%m")
        cond = t(lang, item.condition_key)
        precip = ""
        if item.precipitation_prob is not None and item.precipitation_prob >= 20:
            precip = t(lang, "weekly_weather_precip", prob=item.precipitation_prob)

        text += t(
            lang,
            "weekly_weather_item",
            day_name=day_name,
            date=formatted_date,
            emoji=item.emoji,
            condition=cond,
            temp_max=_fmt_deg(item.temp_max),
            temp_min=_fmt_deg(item.temp_min),
            wind=f"{item.wind_speed_max:.1f}",
            precip=precip,
        )

    return text


def format_alert_message(lang: str, district_name: str, *, aqi: int, pm2_5: float | None) -> str:
    return t(
        lang,
        "alert_message",
        district=district_name,
        aqi=aqi,
        pm25=_value(pm2_5),
        advice=advice_for(lang, level_for(aqi)),
    )


def format_digest_message(
    lang: str,
    district_name: str,
    *,
    aqi: int,
    weather: CurrentWeather | None = None,
    is_home: bool = False,
    other_district_name: str | None = None,
) -> str:
    level = level_for(aqi)
    switch_hint = (
        t(lang, "digest_switch_hint", other_district=other_district_name)
        if other_district_name
        else ""
    )
    key = "digest_message_weather_home" if is_home else "digest_message_weather"
    if weather is not None:
        weather_desc = weather_condition_label(lang, weather.weather_code)
        return t(
            lang,
            key,
            district=district_name,
            weather_emoji=weather.emoji,
            temp=f"{weather.temp:+0.1f}",
            weather_desc=weather_desc,
            emoji=LEVEL_EMOJI[level],
            level=level_label(lang, level),
            aqi=aqi,
            advice=advice_for(lang, level),
            switch_hint=switch_hint,
        )
    return t(
        lang,
        "digest_message_weather_home" if is_home else "digest_message",
        district=district_name,
        aqi=aqi,
        emoji=LEVEL_EMOJI[level],
        level=level_label(lang, level),
        advice=advice_for(lang, level),
        switch_hint=switch_hint,
    )
