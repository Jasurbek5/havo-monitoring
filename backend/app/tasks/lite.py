"""Yengil rejim: Celery beat o'rniga API jarayonining ichida ishlaydigan jadval.

- havo ma'lumotini yangilash: ishga tushgandan bir oz keyin, so'ng har FETCH_INTERVAL_MINUTES da;
- ertalabki xabar: har kuni DAILY_DIGEST_HOUR:00 da (TIMEZONE bo'yicha).

Kutish devor soati (wall clock) bo'yicha tekshiriladi: noutbuk uyqu rejimiga o'tib uyg'onsa,
vaqt to'g'ri hisoblanadi.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, tzinfo

from app.config import Settings
from app.tasks.air_quality import _fetch_all
from app.tasks.notifications import _send_daily_digest

log = logging.getLogger(__name__)

FIRST_FETCH_DELAY_SECONDS = 5
SLEEP_STEP_SECONDS = 30.0
# Kompyuter uxlab, ertalabki xabar vaqti o'tib ketgach uyg'ongan bo'lsa, kech xabar yuborilmaydi
DIGEST_MAX_LATE = timedelta(hours=1)


def next_daily_run(now: datetime, hour: int, tz: tzinfo) -> datetime:
    """`now` dan keyingi birinchi HH:00 (tz bo'yicha)."""
    local = now.astimezone(tz)
    target = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return target


async def _sleep_until(target: datetime) -> None:
    while (remaining := (target - datetime.now(UTC)).total_seconds()) > 0:
        await asyncio.sleep(min(remaining, SLEEP_STEP_SECONDS))


async def _run_job(name: str, job: Callable[[], Awaitable[object]]) -> None:
    try:
        await job()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Jadvaldagi vazifa xato bilan tugadi: %s", name)


async def _every(name: str, job: Callable[[], Awaitable[object]], interval: timedelta) -> None:
    target = datetime.now(UTC) + timedelta(seconds=FIRST_FETCH_DELAY_SECONDS)
    while True:
        await _sleep_until(target)
        await _run_job(name, job)
        target = datetime.now(UTC) + interval


async def _daily(
    name: str, job: Callable[[], Awaitable[object]], hour: int, tz: tzinfo
) -> None:
    while True:
        target = next_daily_run(datetime.now(UTC), hour, tz)
        await _sleep_until(target)
        if datetime.now(UTC) - target > DIGEST_MAX_LATE:
            log.warning("%s: vaqti o'tib ketgan (kompyuter uxlagan bo'lishi mumkin), o'tkazildi", name)
            continue
        await _run_job(name, job)


async def run_lite_scheduler(settings: Settings) -> None:
    log.info(
        "Yengil jadval ishga tushdi: havo har %d daqiqada, ertalabki xabar %02d:00 (%s)",
        settings.fetch_interval_minutes,
        settings.daily_digest_hour,
        settings.timezone,
    )
    await asyncio.gather(
        _every("air.fetch_all", _fetch_all, timedelta(minutes=settings.fetch_interval_minutes)),
        _daily("notify.daily_digest", _send_daily_digest, settings.daily_digest_hour, settings.tz),
    )
