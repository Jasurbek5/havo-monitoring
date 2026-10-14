"""Fon vazifalari uchun resurslar (har bir vazifa ishga tushganda yaratilib, yopiladi).

Celery'da har vazifa o'z event loop'ida ishlaydi; yengil rejimda esa API jarayonining ichida,
shuning uchun kesh umumiy xotiradagi nusxa."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Bot
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.factory import create_bot
from app.config import Settings, get_settings
from app.core.memory_cache import MemoryCache, get_memory_cache
from app.db.session import make_task_session_factory
from app.services.air_quality import AirQualityProvider, build_provider


@dataclass
class TaskContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis | MemoryCache
    provider: AirQualityProvider
    bot: Bot | None


@asynccontextmanager
async def task_context(*, need_bot: bool = False) -> AsyncIterator[TaskContext]:
    """Har bir asyncio.run() uchun alohida engine, Redis va provayder.

    Ulanishlar event loop'ga bog'langan, shuning uchun ularni vazifalar orasida
    bo'lishib bo'lmaydi.
    """
    settings = get_settings()
    if need_bot and not settings.bot_token:
        raise RuntimeError("BOT_TOKEN sozlanmagan")

    engine, factory = make_task_session_factory()
    redis = get_memory_cache() if settings.lite_mode else Redis.from_url(settings.redis_url)
    provider = build_provider(settings)
    bot = create_bot(settings) if need_bot else None
    try:
        yield TaskContext(settings, factory, redis, provider, bot)
    finally:
        if bot is not None:
            await bot.session.close()
        await provider.aclose()
        await redis.aclose()
        await engine.dispose()
