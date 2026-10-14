"""Boshqa hech bir handler ushlamagan xabar va tugmalar."""

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu_kb
from app.core.i18n import t

router = Router(name="fallback")


@router.message(StateFilter(None))
async def unknown_message(message: Message, lang: str) -> None:
    await message.answer(t(lang, "menu_hint"), reply_markup=main_menu_kb(lang))


@router.callback_query()
async def stale_callback(call: CallbackQuery) -> None:
    """Eskirgan tugma bosilganda "yuklanmoqda" belgisini o'chiradi."""
    await call.answer()
