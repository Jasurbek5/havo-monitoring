"""Foydalanuvchiga boradigan xabar matnlarini yig'ish (bot ham, Celery ham shuni ishlatadi)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.aqi import LEVEL_EMOJI, AQILevel, level_for
from app.core.i18n import t


def _value(number: float | None) -> str:
    return "—" if number is None else f"{number:.1f}"


def advice_for(lang: str, level: AQILevel) -> str:
    return t(lang, f"advice_{level.value}")


def level_label(lang: str, level: AQILevel) -> str:
    return t(lang, f"level_{level.value}")


def format_air_message(
    lang: str,
    district_name: str,
    *,
    aqi: int,
    pm2_5: float | None,
    pm10: float | None,
    recorded_at: datetime,
    tz: ZoneInfo,
    stale: bool = False,
) -> str:
    level = level_for(aqi)
    text = t(
        lang,
        "air_message",
        district=district_name,
        emoji=LEVEL_EMOJI[level],
        level=level_label(lang, level),
        aqi=aqi,
        pm25=_value(pm2_5),
        pm10=_value(pm10),
        time=recorded_at.astimezone(tz).strftime("%H:%M"),
        advice=advice_for(lang, level),
    )
    if stale:
        text += t(lang, "air_stale")
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


def format_digest_message(lang: str, district_name: str, *, aqi: int) -> str:
    level = level_for(aqi)
    return t(
        lang,
        "digest_message",
        district=district_name,
        aqi=aqi,
        emoji=LEVEL_EMOJI[level],
        level=level_label(lang, level),
        advice=advice_for(lang, level),
    )
