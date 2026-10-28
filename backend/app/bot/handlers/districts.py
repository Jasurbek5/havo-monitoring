"""Hudud tanlash: Global GPS (reverse geocoding), shahar nomi bo'yicha qidiruv va ro'yxat."""

import logging
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    district_prompt_kb,
    districts_kb,
    main_menu_kb,
    search_results_kb,
)
from app.bot.states import LocationSearchForm
from app.config import Settings
from app.core.i18n import all_translations, t
from app.models import DistrictKind, User
from app.services.districts import (
    get_district,
    get_or_create_district_by_location,
    list_districts,
)
from app.services.geocoding import (
    LocationResult,
    reverse_geocode,
    search_locations,
)

log = logging.getLogger(__name__)

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


@router.message(F.text.in_(all_translations("btn_search_city")))
@router.message(Command("search"))
async def start_city_search(message: Message, state: FSMContext, lang: str) -> None:
    """Shahar yoki tuman qidirishni boshlash."""
    await state.set_state(LocationSearchForm.waiting_for_query)
    await message.answer(t(lang, "ask_search_city"))


@router.message(LocationSearchForm.waiting_for_query, F.text)
async def process_city_search(
    message: Message, state: FSMContext, settings: Settings, lang: str
) -> None:
    """Foydalanuvchi yozgan shahar/tuman nomi bo'yicha global qidirish."""
    query = (message.text or "").strip()
    if query in all_translations("btn_cancel"):
        await state.clear()
        await message.answer(t(lang, "cancelled"), reply_markup=main_menu_kb(lang))
        return

    results = await search_locations(query, settings.owm_api_key, limit=5)
    if not results:
        await message.answer(t(lang, "search_not_found"))
        return

    # FSM ma'lumotlariga saqlab turamiz
    locs_data = [
        {
            "name_uz": loc.name_uz,
            "name_ru": loc.name_ru,
            "name_en": loc.name_en,
            "lat": loc.lat,
            "lon": loc.lon,
            "country": loc.country,
            "admin_area": loc.admin_area,
        }
        for loc in results
    ]
    await state.update_data(search_results=locs_data)

    options = [(i, loc.display_name(lang)) for i, loc in enumerate(results)]
    await message.answer(
        t(lang, "search_results"),
        reply_markup=search_results_kb(options, lang),
    )


@router.callback_query(F.data.startswith("loc:pick:"))
async def pick_search_result(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
) -> None:
    """Qidiruv natijalaridan birini tanlash."""
    parts = (call.data or "").split(":")
    if len(parts) != 3 or not isinstance(call.message, Message):
        await call.answer()
        return

    idx = int(parts[2])
    data = await state.get_data()
    results = data.get("search_results", [])
    if not results or idx >= len(results):
        await call.answer()
        return

    item = results[idx]
    loc = LocationResult(
        name_uz=item["name_uz"],
        name_ru=item["name_ru"],
        name_en=item["name_en"],
        lat=item["lat"],
        lon=item["lon"],
        country=item.get("country", ""),
        admin_area=item.get("admin_area", ""),
    )

    district = await get_or_create_district_by_location(session, loc)
    user.district_id = district.id

    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        t(lang, "district_set", name=district.name(lang)),
        reply_markup=main_menu_kb(lang),
    )
    await call.answer()


@router.callback_query(F.data == "loc:cancel")
async def cancel_search(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(t(lang, "cancelled"), reply_markup=main_menu_kb(lang))
    await call.answer()


@router.message(F.location, StateFilter(None))
async def on_location(
    message: Message, session: AsyncSession, user: User, lang: str, settings: Settings
) -> None:
    """Global GPS: istalgan joylashuv bo'yicha reverse geocoding orqali hududni aniqlash."""
    assert message.location is not None
    lat = message.location.latitude
    lon = message.location.longitude

    loc = await reverse_geocode(lat, lon, settings.owm_api_key, lang=lang)
    district = await get_or_create_district_by_location(session, loc)
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
