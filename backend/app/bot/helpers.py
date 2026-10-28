"""Bot uchun yordamchi funksiyalar (xabarlarni xavfsiz o'chirish)."""

import logging
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

log = logging.getLogger(__name__)


async def safe_delete_message(message: Message | None) -> bool:
    """Xabarni xavfsiz o'chiradi.
    
    Agar xabar mavjud bo'lmasa, allaqachon o'chirilgan bo'lsa yoki Telegram
    o'chirishga ruxsat bermasa (masalan 48 soat o'tgan bo'lsa), xatolik chiqarmaydi.
    """
    if message is None:
        return False
    try:
        await message.delete()
        return True
    except TelegramBadRequest as exc:
        log.debug("Xabarni o'chirib bo'lmadi (id=%s): %s", getattr(message, "message_id", None), exc)
        return False
    except Exception as exc:
        log.debug("Xabarni o'chirishda xatolik: %s", exc)
        return False
