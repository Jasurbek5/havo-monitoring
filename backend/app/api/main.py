"""FastAPI ilovasi: health, Telegram webhook va (polling rejimida) botning o'zi.

Bot rejimlari (BOT_MODE):
- polling: bot shu jarayon ichida fon vazifasi sifatida ishlaydi. Domen va HTTPS shart emas.
  Telegram bir vaqtda faqat bitta polling'ga ruxsat beradi, shuning uchun API'ni bitta
  nusxa va bitta worker bilan ishga tushiring.
- webhook: Telegram yangilanishlarni POST /telegram/webhook ga yuboradi (HTTPS kerak).
"""

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager, suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.bot.factory import create_bot, create_dispatcher
from app.config import get_settings
from app.core.memory_cache import get_memory_cache
from app.db.lite import init_lite_db
from app.db.session import dispose_engine, get_engine, get_session_factory
from app.services.air_quality import build_provider
from app.tasks.lite import run_lite_scheduler

log = logging.getLogger("app")


def _log_polling_result(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Bot polling to'xtadi: %r", exc, exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    # httpx INFO darajasida butun URL'ni yozadi, unda esa OpenWeatherMap kaliti (appid=...) bor
    logging.getLogger("httpx").setLevel(logging.WARNING)

    lite = settings.lite_mode
    redis = get_memory_cache() if lite else Redis.from_url(settings.redis_url)
    provider = build_provider(settings)
    bot: Bot | None = None
    dp: Dispatcher | None = None
    polling_task: asyncio.Task | None = None
    scheduler_task: asyncio.Task | None = None

    if lite:
        await init_lite_db(get_engine(), get_session_factory())
        log.info("Yengil rejim: SQLite, xotiradagi kesh, Celery o'rniga ichki jadval")

    if settings.bot_token:
        bot = create_bot(settings)
        dp = create_dispatcher(
            redis=redis,
            provider=provider,
            settings=settings,
            session_factory=get_session_factory(),
            storage=MemoryStorage() if lite else None,
        )
        allowed = dp.resolve_used_update_types()
        if settings.bot_mode == "webhook":
            if not settings.webhook_base_url or not settings.webhook_secret:
                raise RuntimeError("Webhook rejimi uchun WEBHOOK_BASE_URL va WEBHOOK_SECRET kerak")
            await bot.set_webhook(
                settings.webhook_url, secret_token=settings.webhook_secret, allowed_updates=allowed
            )
            log.info("Webhook o'rnatildi: %s", settings.webhook_url)
        else:
            await bot.delete_webhook()
            polling_task = asyncio.create_task(
                dp.start_polling(bot, handle_signals=False, allowed_updates=allowed),
                name="bot-polling",
            )
            polling_task.add_done_callback(_log_polling_result)
            log.info("Bot polling rejimida ishga tushdi")
    else:
        log.warning("BOT_TOKEN bo'sh: bot ishga tushmadi, faqat API ishlaydi")

    if lite:
        scheduler_task = asyncio.create_task(run_lite_scheduler(settings), name="lite-scheduler")

    app.state.settings = settings
    app.state.redis = redis
    app.state.bot = bot
    app.state.dp = dp
    try:
        yield
    finally:
        for task in (scheduler_task, polling_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        if bot is not None:
            await bot.session.close()
        await provider.aclose()
        await redis.aclose()
        await dispose_engine()


app = FastAPI(title="Havo monitoringi API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Jarayon tirik (Docker healthcheck shuni so'raydi)."""
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Baza va Redis (yengil rejimda: xotiradagi kesh) ishlayaptimi."""
    checks: dict[str, str] = {}
    cache_name = "cache" if request.app.state.settings.lite_mode else "redis"
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
    try:
        await request.app.state.redis.ping()
        checks[cache_name] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks[cache_name] = f"error: {exc.__class__.__name__}"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(checks, status_code=200 if healthy else 503)


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = request.app.state.settings
    bot: Bot | None = request.app.state.bot
    dp: Dispatcher | None = request.app.state.dp
    if settings.bot_mode != "webhook" or bot is None or dp is None:
        raise HTTPException(status_code=404)
    if not hmac.compare_digest(x_telegram_bot_api_secret_token or "", settings.webhook_secret):
        raise HTTPException(status_code=403)

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}