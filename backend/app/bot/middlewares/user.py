import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.i18n import DEFAULT_LANG, LANGS
from app.models import User

_user_lock = asyncio.Lock()


class UserMiddleware(BaseMiddleware):
    """Foydalanuvchini bazadan oladi (yo'q bo'lsa yaratadi) va `user`, `lang` ni beradi.

    DbSessionMiddleware dan keyin ishlashi kerak (`data["session"]` kerak).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data["session"]
        user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
        if user is None:
            async with _user_lock:
                # Parallel task allaqachon yaratganligini qayta tekshiramiz (double-check lock)
                user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
                if user is None:
                    code = (tg_user.language_code or "").lower()
                    if code.startswith("ru"):
                        language = "ru"
                    elif code.startswith("en"):
                        language = "en"
                    else:
                        language = DEFAULT_LANG
                    user = User(telegram_id=tg_user.id, language=language)
                    session.add(user)
                    try:
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))

        if user is not None and not user.is_active:
            user.is_active = True  # botni qayta ishga tushirdi: ogohlantirishlarni tiklaymiz

        if user is not None:
            if user.language not in LANGS:
                user.language = DEFAULT_LANG
            data["user"] = user
            data["lang"] = user.language
        return await handler(event, data)
