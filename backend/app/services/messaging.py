"""Telegram'ga xavfsiz xabar yuborish (ommaviy xabarlar uchun ham)."""

import asyncio
import enum
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

log = logging.getLogger(__name__)


class SendStatus(enum.StrEnum):
    OK = "ok"
    BLOCKED = "blocked"  # foydalanuvchi botni bloklagan yoki akkaunti o'chirilgan
    FAILED = "failed"


@dataclass
class BroadcastResult:
    sent: int = 0
    failed: int = 0
    blocked: list[int] = field(default_factory=list)  # telegram_id lar


async def safe_send(bot: Bot, chat_id: int, text: str, *, retries: int = 2, **kwargs) -> SendStatus:
    for _ in range(retries + 1):
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return SendStatus.OK
        except TelegramRetryAfter as exc:  # Telegram limiti: kutib, qayta urinamiz
            await asyncio.sleep(exc.retry_after + 0.5)
        except TelegramForbiddenError:
            return SendStatus.BLOCKED
        except TelegramAPIError as exc:
            log.warning("Xabar yuborilmadi (chat_id=%s): %r", chat_id, exc)
            return SendStatus.FAILED
    return SendStatus.FAILED


async def send_many(
    bot: Bot,
    messages: Iterable[tuple[int, str]],
    *,
    rate_per_second: float = 25.0,
    **kwargs,
) -> BroadcastResult:
    """(telegram_id, matn) juftliklarini Telegram limitidan (~30/s) past tezlikda yuboradi."""
    result = BroadcastResult()
    interval = 1.0 / rate_per_second
    for chat_id, text in messages:
        status = await safe_send(bot, chat_id, text, **kwargs)
        if status is SendStatus.OK:
            result.sent += 1
        elif status is SendStatus.BLOCKED:
            result.blocked.append(chat_id)
        else:
            result.failed += 1
        await asyncio.sleep(interval)
    return result
