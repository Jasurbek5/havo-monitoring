"""Ogohlantirishlar, ertalabki xabar vaqti, uy hududi va til sozlamalari menyusi."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.districts import send_district_list
from app.bot.helpers import safe_delete_message
from app.bot.keyboards import (
    digest_time_kb,
    home_settings_kb,
    language_kb,
    settings_kb,
    timezone_display_name,
    timezone_kb,
)
from app.core.i18n import all_translations, t
from app.models import User

router = Router(name="settings")


@router.message(F.text.in_(all_translations("btn_alerts")))
async def alerts_menu(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await safe_delete_message(message)
    await state.clear()
    await message.answer(t(lang, "settings_title"), reply_markup=settings_kb(user, lang))


@router.message(F.text.in_(all_translations("btn_language")))
async def language_menu(message: Message, state: FSMContext, lang: str) -> None:
    await safe_delete_message(message)
    await state.clear()
    await message.answer(t(lang, "choose_language"), reply_markup=language_kb())


@router.callback_query(F.data.in_({"set:alert", "set:digest"}))
async def toggle_setting(call: CallbackQuery, user: User, lang: str) -> None:
    if user.district_id is None and user.home_district_id is None:
        await call.answer(t(lang, "need_district"), show_alert=True)
        return
    if call.data == "set:alert":
        user.alert_enabled = not user.alert_enabled
    else:
        user.daily_digest = not user.daily_digest

    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=settings_kb(user, lang))
    await call.answer()


@router.callback_query(F.data == "set:time")
async def choose_time_menu(call: CallbackQuery, user: User, lang: str) -> None:
    """Ertalabki xabar vaqtini tanlash menyusi."""
    await call.answer()
    if isinstance(call.message, Message):
        current_time = user.digest_time or "07:00"
        await call.message.edit_text(
            t(lang, "choose_digest_time"),
            reply_markup=digest_time_kb(current_time, lang),
        )


@router.callback_query(F.data.startswith("time:pick:"))
async def pick_digest_time(call: CallbackQuery, user: User, lang: str) -> None:
    """Yangi ertalabki xabar vaqtini saqlash."""
    new_time = (call.data or "").rsplit(":", 1)[1]
    user.digest_time = new_time
    await call.answer(t(lang, "digest_time_set", time=new_time))
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "settings_title"),
            reply_markup=settings_kb(user, lang),
        )


@router.callback_query(F.data == "set:tz")
async def choose_timezone_menu(call: CallbackQuery, user: User, lang: str) -> None:
    """Vaqt mintaqasini tanlash menyusi."""
    await call.answer()
    if isinstance(call.message, Message):
        current_tz = getattr(user, "timezone", "auto")
        await call.message.edit_text(
            t(lang, "choose_timezone"),
            reply_markup=timezone_kb(current_tz, lang),
        )


@router.callback_query(F.data.startswith("tz:pick:"))
async def pick_timezone(call: CallbackQuery, user: User, lang: str) -> None:
    """Yangi vaqt mintaqasini saqlash."""
    new_tz = (call.data or "").split(":", 2)[2]
    user.timezone = new_tz
    tz_label = timezone_display_name(new_tz, lang)
    await call.answer(t(lang, "timezone_set", tz=tz_label))
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "settings_title"),
            reply_markup=settings_kb(user, lang),
        )


@router.callback_query(F.data == "set:home")
async def home_menu(call: CallbackQuery, user: User, lang: str) -> None:
    """Uy hududi sozlamasi menyusi."""
    await call.answer()
    home_name = user.home_district.name(lang) if user.home_district else "—"
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "home_title", name=home_name),
            reply_markup=home_settings_kb(user, lang),
        )


@router.callback_query(F.data == "home:set_current")
async def set_current_as_home(call: CallbackQuery, user: User, lang: str) -> None:
    """Hozirgi ko'rilayotgan hududni uy qilib belgilash."""
    if user.district:
        user.home_district_id = user.district_id
        await call.answer(t(lang, "home_district_set", name=user.district.name(lang)))
    else:
        await call.answer(t(lang, "need_district"), show_alert=True)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "settings_title"),
            reply_markup=settings_kb(user, lang),
        )


@router.callback_query(F.data == "home:clear")
async def clear_home_district(call: CallbackQuery, user: User, lang: str) -> None:
    """Uy hududini bekor qilish."""
    user.home_district_id = None
    await call.answer(t(lang, "home_district_cleared"))
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "settings_title"),
            reply_markup=settings_kb(user, lang),
        )


@router.callback_query(F.data == "home:choose_list")
async def choose_home_from_list(
    call: CallbackQuery, session: AsyncSession, lang: str
) -> None:
    """Uy hududini ro'yxatdan tanlash."""
    await call.answer()
    if isinstance(call.message, Message):
        await send_district_list(call.message, session, lang, mode="set_home")


@router.callback_query(F.data == "set:back")
async def back_to_settings(call: CallbackQuery, user: User, lang: str) -> None:
    """Asosiy sozlamalar menyusiga qaytish."""
    await call.answer()
    if isinstance(call.message, Message):
        await call.message.edit_text(
            t(lang, "settings_title"),
            reply_markup=settings_kb(user, lang),
        )
