"""Bot va Dispatcher'ni yig'ish."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers import get_routers
from app.bot.middlewares import DbSessionMiddleware, UserMiddleware
from app.config import Settings
from app.services.air_quality import AirQualityProvider

FSM_TTL_SECONDS = 3600  # tashlab ketilgan murojaat holati 1 soatdan keyin o'chadi


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    *,
    redis: Redis | None,
    provider: AirQualityProvider,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    storage: BaseStorage | None = None,
) -> Dispatcher:
    """`redis`, `provider`, `settings` handlerlarga nom bo'yicha uzatiladi (workflow_data).

    `storage` berilmasa FSM holati Redis'da saqlanadi (testlarda MemoryStorage beriladi).
    """
    if storage is None:
        if redis is None:
            raise ValueError("FSM saqlash uchun redis yoki storage kerak")
        storage = RedisStorage(redis, state_ttl=FSM_TTL_SECONDS, data_ttl=FSM_TTL_SECONDS)
    dp = Dispatcher(storage=storage, redis=redis, provider=provider, settings=settings)

    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())

    dp.include_routers(*get_routers())
    return dp
