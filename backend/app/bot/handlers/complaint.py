"""Murojaat yuborish: FSM (tur -> rasm -> joylashuv -> tavsif -> tasdiqlash)."""

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.helpers import safe_delete_message
from app.bot.keyboards import (
    cancel_kb,
    categories_kb,
    complaint_location_kb,
    confirm_kb,
    district_prompt_kb,
    main_menu_kb,
    photo_kb,
)
from app.bot.states import ComplaintForm
from app.config import Settings
from app.core.i18n import all_translations, t
from app.models import ComplaintCategory, District, User
from app.services.complaints import count_recent, create_complaint, download_photo
from app.services.districts import nearest_district

log = logging.getLogger(__name__)
router = Router(name="complaint")

CATEGORIES = {category.value: category for category in ComplaintCategory}
MIN_TEXT, MAX_TEXT = 5, 1000


async def _resolve_district(
    session: AsyncSession, data: dict, user: User, settings: Settings
) -> District | None:
    """Koordinatadan eng yaqin hudud; topilmasa foydalanuvchining o'z hududi."""
    found = await nearest_district(session, data["lat"], data["lon"], settings.max_district_distance_km)
    return found[0] if found else user.district


async def _finish(message: Message, state: FSMContext, lang: str, text_key: str, **kwargs) -> None:
    await state.clear()
    await message.answer(t(lang, text_key, **kwargs), reply_markup=main_menu_kb(lang))


# --- Bekor qilish -----------------------------------------------------------


@router.message(Command("cancel"))
@router.message(StateFilter(ComplaintForm), F.text.in_(all_translations("btn_cancel")))
async def cancel_by_text(message: Message, state: FSMContext, lang: str) -> None:
    await _finish(message, state, lang, "cancelled")


@router.callback_query(F.data == "cmp:cancel")
async def cancel_by_button(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)
        await _finish(call.message, state, lang, "cancelled")
    await call.answer()


# --- 1. Tur -----------------------------------------------------------------


@router.message(F.text.in_(all_translations("btn_complaint")))
async def start_complaint(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
    settings: Settings,
) -> None:
    await safe_delete_message(message)
    await state.clear()
    if user.district_id is None:
        await message.answer(t(lang, "need_district"), reply_markup=district_prompt_kb(lang))
        return
    if await count_recent(session, user.id) >= settings.max_complaints_per_day:
        await message.answer(t(lang, "cmp_limit", limit=settings.max_complaints_per_day))
        return
    await state.set_state(ComplaintForm.category)
    await message.answer(t(lang, "cmp_choose_category"), reply_markup=categories_kb(lang))


@router.callback_query(ComplaintForm.category, F.data.startswith("cat:"))
async def choose_category(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    value = (call.data or "").split(":", 1)[1]
    if value not in CATEGORIES or not isinstance(call.message, Message):
        await call.answer()
        return
    await state.update_data(category=value)
    await state.set_state(ComplaintForm.photo)
    await call.message.edit_text(t(lang, "cmp_send_photo"), reply_markup=photo_kb(lang))
    await call.answer()


# --- 2. Rasm ----------------------------------------------------------------


async def _ask_location(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ComplaintForm.location)
    await message.answer(t(lang, "cmp_send_location"), reply_markup=complaint_location_kb(lang))


@router.message(ComplaintForm.photo, F.photo)
async def got_photo(message: Message, state: FSMContext, lang: str) -> None:
    assert message.photo
    await state.update_data(photo_file_id=message.photo[-1].file_id)  # eng katta o'lcham
    await _ask_location(message, state, lang)


@router.callback_query(ComplaintForm.photo, F.data == "cmp:skip_photo")
async def skip_photo(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if isinstance(call.message, Message):
        await state.update_data(photo_file_id=None)
        await call.message.edit_reply_markup(reply_markup=None)
        await _ask_location(call.message, state, lang)
    await call.answer()


@router.message(ComplaintForm.photo)
async def photo_expected(message: Message, lang: str) -> None:
    await message.answer(t(lang, "cmp_photo_expected"))


# --- 3. Joylashuv -----------------------------------------------------------


async def _ask_text(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ComplaintForm.text)
    await message.answer(t(lang, "cmp_write_text"), reply_markup=cancel_kb(lang))


@router.message(ComplaintForm.location, F.location)
async def got_location(message: Message, state: FSMContext, lang: str) -> None:
    assert message.location
    await state.update_data(
        lat=message.location.latitude, lon=message.location.longitude, approx=False
    )
    await _ask_text(message, state, lang)


@router.message(ComplaintForm.location, F.text.in_(all_translations("btn_use_my_district")))
async def use_my_district(message: Message, state: FSMContext, user: User, lang: str) -> None:
    district = user.district
    if district is None:
        await message.answer(t(lang, "cmp_location_expected"))
        return
    await state.update_data(lat=district.lat, lon=district.lon, approx=True)
    await _ask_text(message, state, lang)


@router.message(ComplaintForm.location)
async def location_expected(message: Message, lang: str) -> None:
    await message.answer(t(lang, "cmp_location_expected"))


# --- 4. Tavsif --------------------------------------------------------------


@router.message(ComplaintForm.text, F.text)
async def got_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
    settings: Settings,
) -> None:
    text = (message.text or "").strip()
    if not MIN_TEXT <= len(text) <= MAX_TEXT:
        await message.answer(t(lang, "cmp_text_invalid"))
        return

    await state.update_data(text=text)
    data = await state.get_data()
    district = await _resolve_district(session, data, user, settings)

    if data.get("approx"):
        location = t(lang, "loc_approx")
    else:
        location = f"{data['lat']:.5f}, {data['lon']:.5f}"

    summary = t(
        lang,
        "cmp_confirm",
        category=t(lang, f"cat_{data['category']}"),
        district=district.name(lang) if district else "—",
        location=location,
        photo=t(lang, "photo_yes" if data.get("photo_file_id") else "photo_no"),
        text=html.escape(text),
    )
    await state.set_state(ComplaintForm.confirm)
    await message.answer(summary, reply_markup=confirm_kb(lang))


@router.message(ComplaintForm.text)
async def text_expected(message: Message, lang: str) -> None:
    await message.answer(t(lang, "cmp_text_invalid"))


# --- 5. Tasdiqlash ----------------------------------------------------------


@router.callback_query(ComplaintForm.confirm, F.data == "cmp:confirm")
async def confirm(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
    settings: Settings,
    bot: Bot,
) -> None:
    if not isinstance(call.message, Message):
        await call.answer()
        return
    message = call.message

    data = await state.get_data()
    # Qayta bosib yuborishdan (ikki marta saqlashdan) himoya: holatni darhol tozalaymiz.
    await state.clear()
    await message.edit_reply_markup(reply_markup=None)
    await call.answer()

    if not all(key in data for key in ("category", "lat", "lon", "text")):
        await message.answer(t(lang, "cmp_session_expired"), reply_markup=main_menu_kb(lang))
        return
    if await count_recent(session, user.id) >= settings.max_complaints_per_day:
        await message.answer(
            t(lang, "cmp_limit", limit=settings.max_complaints_per_day),
            reply_markup=main_menu_kb(lang),
        )
        return

    photo_file_id = data.get("photo_file_id")
    photo_path = (
        await download_photo(bot, photo_file_id, settings.media_dir) if photo_file_id else None
    )
    district = await _resolve_district(session, data, user, settings)

    try:
        complaint = await create_complaint(
            session,
            user_id=user.id,
            district_id=district.id if district else None,
            category=CATEGORIES[data["category"]],
            lat=data["lat"],
            lon=data["lon"],
            location_is_approx=bool(data.get("approx")),
            text=data["text"],
            photo_file_id=photo_file_id,
            photo_path=photo_path,
        )
    except SQLAlchemyError:
        log.exception("Murojaatni saqlashda xato")
        await session.rollback()
        await message.answer(t(lang, "cmp_error"), reply_markup=main_menu_kb(lang))
        return

    await message.answer(t(lang, "cmp_saved", id=complaint.id), reply_markup=main_menu_kb(lang))
