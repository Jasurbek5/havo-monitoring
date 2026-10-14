"""Ogohlantirishlar sozlamalari va til almashtirish menyusi."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import language_kb, settings_kb
from app.core.i18n import all_translations, t
from app.models import User

router = Router(name="settings")


@router.message(F.text.in_(all_translations("btn_alerts")))
async def alerts_menu(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await state.clear()
    await message.answer(t(lang, "settings_title"), reply_markup=settings_kb(user, lang))


@router.message(F.text.in_(all_translations("btn_language")))
async def language_menu(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(t(lang, "choose_language"), reply_markup=language_kb())


@router.callback_query(F.data.in_({"set:alert", "set:digest"}))
async def toggle_setting(call: CallbackQuery, user: User, lang: str) -> None:
    if user.district_id is None:
        # Hududsiz ogohlantirish yuborib bo'lmaydi
        await call.answer(t(lang, "need_district"), show_alert=True)
        return
    if call.data == "set:alert":
        user.alert_enabled = not user.alert_enabled
    else:
        user.daily_digest = not user.daily_digest

    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=settings_kb(user, lang))
    await call.answer()
