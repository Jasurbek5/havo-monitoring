"""Havo sifati: joriy holat, yangilash va boshqa hududni ko'rish."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.districts import send_district_list
from app.bot.keyboards import air_kb, district_prompt_kb
from app.config import Settings
from app.core.i18n import all_translations, t
from app.core.messages import format_air_message
from app.models import District, User
from app.services.air_quality import AirQualityProvider, ProviderError, get_current_reading
from app.services.districts import get_district

router = Router(name="air")


async def build_air_text(
    session: AsyncSession,
    redis: Redis | None,
    provider: AirQualityProvider,
    settings: Settings,
    district: District,
    lang: str,
) -> str:
    try:
        reading = await get_current_reading(
            session, redis, provider, district, ttl_minutes=settings.reading_ttl_minutes
        )
    except ProviderError:
        return t(lang, "air_unavailable")
    return format_air_message(
        lang,
        district.name(lang),
        aqi=reading.aqi,
        pm2_5=reading.pm2_5,
        pm10=reading.pm10,
        recorded_at=reading.recorded_at,
        tz=settings.tz,
        stale=reading.stale,
    )


@router.message(F.text.in_(all_translations("btn_air")))
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
    await state.clear()
    district = user.district
    if district is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    text = await build_air_text(session, redis, provider, settings, district, lang)
    await message.answer(text, reply_markup=air_kb(lang, district.id))


@router.callback_query(F.data.startswith("air:refresh:"))
async def refresh_air(
    call: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    provider: AirQualityProvider,
    settings: Settings,
    lang: str,
) -> None:
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        await call.answer()
        return

    text = await build_air_text(session, redis, provider, settings, district, lang)
    try:
        await call.message.edit_text(text, reply_markup=air_kb(lang, district.id))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await call.answer(t(lang, "air_not_updated"))
        return
    await call.answer()


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
