"""/start va til tanlash."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import district_prompt_kb, language_kb, main_menu_kb
from app.core.i18n import LANGS, t
from app.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await state.clear()
    if user.district_id is None:
        # Yangi foydalanuvchi: avval til, keyin hudud
        await message.answer(t(lang, "choose_language"), reply_markup=language_kb())
        return
    await message.answer(t(lang, "welcome_back"), reply_markup=main_menu_kb(lang))


@router.callback_query(F.data.startswith("lang:"))
async def on_language(call: CallbackQuery, user: User) -> None:
    new_lang = (call.data or "").split(":", 1)[1]
    if new_lang not in LANGS or not isinstance(call.message, Message):
        await call.answer()
        return

    user.language = new_lang
    await call.message.edit_reply_markup(reply_markup=None)
    if user.district_id is None:
        await call.message.answer(t(new_lang, "welcome"))
        await call.message.answer(t(new_lang, "ask_district"), reply_markup=district_prompt_kb(new_lang))
    else:
        await call.message.answer(t(new_lang, "lang_set"), reply_markup=main_menu_kb(new_lang))
    await call.answer()
