"""Hudud tanlash: GPS orqali, ro'yxatdan va "Hududim" bo'limi."""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import district_prompt_kb, districts_kb, main_menu_kb
from app.config import Settings
from app.core.i18n import all_translations, t
from app.models import DistrictKind, User
from app.services.districts import get_district, list_districts, nearest_district

router = Router(name="districts")


async def send_district_list(
    message: Message, session: AsyncSession, lang: str, *, mode: str, group: str = "city"
) -> None:
    kind = DistrictKind.CITY_DISTRICT if group == "city" else DistrictKind.REGION
    districts = await list_districts(session, kind)
    await message.answer(
        t(lang, "choose_district"),
        reply_markup=districts_kb(districts, lang, mode=mode, group=group),
    )


@router.message(F.text.in_(all_translations("btn_district")))
async def my_district(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await state.clear()
    name = user.district.name(lang) if user.district else "—"
    await message.answer(t(lang, "my_district", name=name), reply_markup=district_prompt_kb(lang))


@router.message(F.text.in_(all_translations("btn_choose_list")))
async def choose_from_list(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    await state.clear()
    await send_district_list(message, session, lang, mode="set")


@router.message(F.location, StateFilter(None))
async def on_location(
    message: Message, session: AsyncSession, user: User, lang: str, settings: Settings
) -> None:
    """GPS yuborilganda eng yaqin hududni topadi. Koordinata saqlanmaydi."""
    assert message.location is not None
    found = await nearest_district(
        session,
        message.location.latitude,
        message.location.longitude,
        settings.max_district_distance_km,
    )
    if found is None:
        await message.answer(t(lang, "district_not_found"))
        await send_district_list(message, session, lang, mode="set")
        return

    district, _distance = found
    user.district_id = district.id
    await message.answer(
        t(lang, "district_detected", name=district.name(lang)), reply_markup=main_menu_kb(lang)
    )


@router.callback_query(F.data.startswith("dist:list:"))
async def switch_list(call: CallbackQuery, session: AsyncSession, lang: str) -> None:
    """Toshkent tumanlari <-> viloyatlar ro'yxati almashinuvi."""
    parts = (call.data or "").split(":")
    if len(parts) != 4 or not isinstance(call.message, Message):
        await call.answer()
        return
    _, _, mode, group = parts
    kind = DistrictKind.CITY_DISTRICT if group == "city" else DistrictKind.REGION
    districts = await list_districts(session, kind)
    await call.message.edit_reply_markup(
        reply_markup=districts_kb(districts, lang, mode=mode, group=group)
    )
    await call.answer()


@router.callback_query(F.data.startswith("dist:set:"))
async def set_district(
    call: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    district_id = int((call.data or "").rsplit(":", 1)[1])
    district = await get_district(session, district_id)
    if district is None or not isinstance(call.message, Message):
        await call.answer()
        return

    user.district_id = district.id
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        t(lang, "district_set", name=district.name(lang)), reply_markup=main_menu_kb(lang)
    )
    await call.answer()
