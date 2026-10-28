"""Havo sifati va ob-havo: joriy holat, to'liq ob-havo, haftalik prognoz va yangilash."""

import asyncio
import logging
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.districts import send_district_list
from app.bot.keyboards import air_kb, district_prompt_kb, today_weather_kb, weekly_weather_kb
from app.config import Settings
from app.core.i18n import all_translations, t
from app.core.messages import (
    format_air_message,
    format_full_weather_message,
    format_weekly_forecast_message,
)
from app.models import District, User
from app.services.air_quality import AirQualityProvider, ProviderError, get_current_reading
from app.services.districts import get_district
from app.services.weather import (
    CurrentWeather,
    WeatherError,
    get_current_weather,
    get_weekly_weather,
)

log = logging.getLogger(__name__)

router = Router(name="air")


async def build_air_text(
    session: AsyncSession,
    redis: Redis | None,
    provider: AirQualityProvider,
    settings: Settings,
    district: District,
    lang: str,
) -> str:
    """Umumiy xabar: havo sifati va ob-havoni parallel oladi (maksimal tezlik)."""
    reading_coro = get_current_reading(
        session, redis, provider, district, ttl_minutes=settings.reading_ttl_minutes
    )
    weather_coro = get_current_weather(
        redis, district, settings.owm_api_key, ttl_minutes=settings.reading_ttl_minutes
    )
    reading_res, weather_res = await asyncio.gather(
        reading_coro, weather_coro, return_exceptions=True
    )

    if isinstance(reading_res, Exception):
        log.warning("Havo sifati olinmadi (%s): %r", district.slug, reading_res)
        return t(lang, "air_unavailable")

    weather = weather_res if not isinstance(weather_res, Exception) else None

    return format_air_message(
        lang,
        district.name(lang),
        aqi=reading_res.aqi,
        pm2_5=reading_res.pm2_5,
        pm10=reading_res.pm10,
        recorded_at=reading_res.recorded_at,
        tz=settings.tz,
        stale=reading_res.stale,
        weather=weather,
    )


async def build_today_weather_text(
    redis: Redis | None,
    settings: Settings,
    district: District,
    lang: str,
) -> str:
    """Bugungi to'liq ob-havo matni."""
    try:
        weather = await get_current_weather(
            redis, district, settings.owm_api_key, ttl_minutes=settings.reading_ttl_minutes
        )
    except (WeatherError, Exception) as exc:
        log.warning("Bugungi ob-havo olinmadi (%s): %r", district.slug, exc)
        return t(lang, "weather_unavailable")

    return format_full_weather_message(lang, district.name(lang), weather, tz=settings.tz)


async def build_weekly_weather_text(
    redis: Redis | None,
    settings: Settings,
    district: District,
    lang: str,
) -> str:
    """7 kunlik ob-havo prognozi matni (Open-Meteo va OWM zaxirasi bilan)."""
    try:
        weekly = await get_weekly_weather(
            redis, district, owm_api_key=settings.owm_api_key, ttl_minutes=120
        )
    except (WeatherError, Exception) as exc:
        log.warning("Haftalik ob-havo olinmadi (%s): %r", district.slug, exc)
        return t(lang, "weather_unavailable")

    return format_weekly_forecast_message(lang, district.name(lang), weekly, tz=settings.tz)


# ---------------------------------------------------------------------------
# Message handlerlar (Reply keyboard)
# ---------------------------------------------------------------------------


AIR_BUTTONS = all_translations("btn_air") | {"🌫 Havo sifati", "🌫 Качество воздуха", "🌫 Air quality"}
WEATHER_BUTTONS = all_translations("btn_weather") | {"🌤 Ob-havo", "🌤 Погода", "🌤 Weather", "🌤 To'liq ob-havo"}


@router.message(F.text.in_(AIR_BUTTONS))
async def show_air(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """Umumiy xabar (Ob-havo + Havo sifati)."""
    await state.clear()
    district = user.district
    if district is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    text = await build_air_text(session, redis, provider, settings, district, lang)
    await message.answer(text, reply_markup=air_kb(lang, district.id))


@router.message(F.text.in_(WEATHER_BUTTONS))
async def show_today_weather(
    message: Message,
    state: FSMContext,
    redis: Redis,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """Bugungi to'liq ob-havo."""
    await state.clear()
    district = user.district
    if district is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    text = await build_today_weather_text(redis, settings, district, lang)
    await message.answer(text, reply_markup=today_weather_kb(lang, district.id))


# ---------------------------------------------------------------------------
# Callback handlerlar (Inline buttons)
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("air:refresh:"))
async def refresh_air(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    lang: str,
) -> None:
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    text = await build_air_text(session, redis, provider, settings, district, lang)
    try:
        await call.message.edit_text(text, reply_markup=air_kb(lang, district.id))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.startswith("weather:today:"))
async def view_today_weather(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    lang: str,
) -> None:
    """Bugungi to'liq ob-havoga o'tish yoki yangilash."""
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    text = await build_today_weather_text(redis, settings, district, lang)
    try:
        await call.message.edit_text(text, reply_markup=today_weather_kb(lang, district.id))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.startswith("weather:week:"))
async def view_weekly_weather(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    lang: str,
) -> None:
    """7 kunlik haftalik prognozga o'tish yoki yangilash."""
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    text = await build_weekly_weather_text(redis, settings, district, lang)
    try:
        await call.message.edit_text(text, reply_markup=weekly_weather_kb(lang, district.id))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data == "air:other")
async def pick_other_district(call: CallbackQuery, session: AsyncSession, lang: str) -> None:
    if not isinstance(call.message, Message):
        await call.answer()
        return
    await send_district_list(call.message, session, lang, mode="view")
    await call.answer()


@router.callback_query(F.data.startswith("dist:view:"))
async def view_district(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    lang: str,
) -> None:
    """Boshqa hudud havosini ko'rsatadi (foydalanuvchining saqlangan hududi o'zgarmaydi)."""
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        await call.answer()
        return

    text = await build_air_text(session, redis, provider, settings, district, lang)
    await call.message.edit_text(text, reply_markup=air_kb(lang, district.id))
    await call.answer()
