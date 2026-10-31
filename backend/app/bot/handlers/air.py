"""Havo sifati va ob-havo: joriy holat, to'liq ob-havo, haftalik prognoz va yangilash."""

import asyncio
import logging
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.helpers import safe_delete_message
from app.bot.keyboards import air_kb, district_prompt_kb, today_weather_kb, weekly_weather_kb
from app.bot.states import LocationSearchForm
from app.config import Settings
from app.core.i18n import all_translations, t
from app.core.messages import (
    format_air_message,
    format_full_weather_message,
    format_weekly_forecast_message,
    resolve_effective_tz,
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
    user: User | None = None,
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
    tz, tz_label = resolve_effective_tz(
        getattr(user, "timezone", "auto") if user else None,
        weather,
        settings.tz,
    )

    return format_air_message(
        lang,
        district.name(lang),
        aqi=reading_res.aqi,
        pm2_5=reading_res.pm2_5,
        pm10=reading_res.pm10,
        recorded_at=reading_res.recorded_at,
        tz=tz,
        tz_label=tz_label,
        stale=reading_res.stale,
        weather=weather,
    )


async def build_today_weather_text(
    redis: Redis | None,
    settings: Settings,
    district: District,
    lang: str,
    user: User | None = None,
) -> str:
    """Bugungi to'liq ob-havo matni."""
    try:
        weather = await get_current_weather(
            redis, district, settings.owm_api_key, ttl_minutes=settings.reading_ttl_minutes
        )
    except (WeatherError, Exception) as exc:
        log.warning("Bugungi ob-havo olinmadi (%s): %r", district.slug, exc)
        return t(lang, "weather_unavailable")

    tz, tz_label = resolve_effective_tz(
        getattr(user, "timezone", "auto") if user else None,
        weather,
        settings.tz,
    )

    return format_full_weather_message(
        lang,
        district.name(lang),
        weather,
        tz=tz,
        tz_label=tz_label,
    )


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


def get_switch_context(user: User, current_district_id: int) -> tuple[District | None, bool]:
    """Qaytadi: (switch_district, is_home).

    Foydalanuvchi uyda bo'lsa, oxirgi boshqa hududga o'tish tugmasi chiqadi;
    boshqa hududda bo'lsa, uyga qaytish tugmasi chiqadi.
    """
    home = user.home_district
    current = user.district
    if not home:
        return None, False
    if current and home.id != current.id:
        if current_district_id == home.id:
            return current, True
        return home, False
    if current_district_id != home.id:
        return home, False
    return None, False


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
    await safe_delete_message(message)
    await state.clear()
    district = user.district or user.home_district
    if district is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_air_text(session, redis, provider, settings, district, lang, user=user)
    await message.answer(
        text,
        reply_markup=air_kb(
            lang,
            district.id,
            switch_district=switch_district,
            is_home=is_home,
            web_app_url=settings.miniapp_url or None,
        ),
    )


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
    await safe_delete_message(message)
    await state.clear()
    district = user.district or user.home_district
    if district is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_today_weather_text(redis, settings, district, lang, user=user)
    await message.answer(
        text,
        reply_markup=today_weather_kb(
            lang,
            district.id,
            switch_district=switch_district,
            is_home=is_home,
            web_app_url=settings.miniapp_url or None,
        ),
    )


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
    user: User,
    lang: str,
) -> None:
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_air_text(session, redis, provider, settings, district, lang, user=user)
    try:
        await call.message.edit_text(
            text,
            reply_markup=air_kb(
                lang,
                district.id,
                switch_district=switch_district,
                is_home=is_home,
                web_app_url=settings.miniapp_url or None,
            ),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.startswith("air:switch:"))
async def switch_air_district(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """Uy va oxirgi tanlangan boshqa hudud o'rtasida 1 bosishda tezkor o'tish."""
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_air_text(session, redis, provider, settings, district, lang, user=user)
    try:
        await call.message.edit_text(
            text,
            reply_markup=air_kb(
                lang,
                district.id,
                switch_district=switch_district,
                is_home=is_home,
                web_app_url=settings.miniapp_url or None,
            ),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.startswith("weather:today:"))
async def view_today_weather(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """Bugungi to'liq ob-havoga o'tish yoki yangilash."""
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_today_weather_text(redis, settings, district, lang, user=user)
    try:
        await call.message.edit_text(
            text,
            reply_markup=today_weather_kb(
                lang,
                district.id,
                switch_district=switch_district,
                is_home=is_home,
                web_app_url=settings.miniapp_url or None,
            ),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.startswith("weather:week:"))
async def view_weekly_weather(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """7 kunlik haftalik prognozga o'tish yoki yangilash."""
    await call.answer()
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        return

    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_weekly_weather_text(redis, settings, district, lang)
    try:
        await call.message.edit_text(
            text,
            reply_markup=weekly_weather_kb(
                lang,
                district.id,
                switch_district=switch_district,
                is_home=is_home,
                web_app_url=settings.miniapp_url or None,
            ),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data.in_({"air:search", "air:other"}))
async def search_other_district(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    await state.set_state(LocationSearchForm.waiting_for_query)
    prompt_msg = await call.message.answer(t(lang, "ask_search_city"))
    await state.update_data(prompt_msg_id=prompt_msg.message_id)


@router.callback_query(F.data.startswith("dist:view:"))
async def view_district(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    user: User,
    lang: str,
) -> None:
    """Boshqa hudud havosini ko'rsatadi (foydalanuvchining saqlangan hududi o'zgarmaydi)."""
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        await call.answer()
        return

    switch_district, is_home = get_switch_context(user, district.id)
    text = await build_air_text(session, redis, provider, settings, district, lang, user=user)
    await call.message.edit_text(
        text,
        reply_markup=air_kb(
            lang,
            district.id,
            switch_district=switch_district,
            is_home=is_home,
            web_app_url=settings.miniapp_url or None,
        ),
    )
    await call.answer()
