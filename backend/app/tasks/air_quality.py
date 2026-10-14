"""Har 30 daqiqada Toshkent tumanlari uchun havo ma'lumotini yangilash."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import Settings
from app.models import District
from app.services.air_quality import ProviderError, cache_reading, fetch_air_quality, store_reading
from app.services.alerts import update_alert_state
from app.tasks.background import spawn
from app.tasks.celery_app import celery_app
from app.tasks.notifications import _send_district_alert, send_district_alert
from app.tasks.runtime import task_context

log = logging.getLogger(__name__)

CONCURRENCY = 5  # provayderga bir vaqtda ko'pi bilan 5 ta so'rov


def _dispatch_alert(settings: Settings, district_id: int, aqi: int, pm2_5: float | None) -> None:
    """Celery'da xabarni navbatga qo'yadi; yengil rejimda shu jarayonning ichida fonda yuboradi."""
    if settings.lite_mode:
        spawn(_send_district_alert(district_id, aqi, pm2_5), name=f"alert-{district_id}")
    else:
        send_district_alert.delay(district_id, aqi, pm2_5)


@celery_app.task(name="air.fetch_all")
def fetch_all() -> dict[str, int]:
    return asyncio.run(_fetch_all())


async def _fetch_all() -> dict[str, int]:
    alerts: list[tuple[int, int, float | None]] = []
    stored = failed = 0

    async with task_context() as ctx, ctx.session_factory() as session:
        settings = ctx.settings
        stmt = select(District).where(
            District.is_active.is_(True), District.poll_enabled.is_(True)
        )
        districts = list((await session.scalars(stmt)).all())

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(district: District):
            async with semaphore:
                try:
                    return district, await fetch_air_quality(district, ctx.provider)
                except ProviderError as exc:
                    log.warning("%s: ma'lumot olinmadi: %s", district.slug, exc)
                    return district, None

        results = await asyncio.gather(*(fetch_one(d) for d in districts))

        now = datetime.now(UTC)
        for district, reading in results:
            if reading is None:
                failed += 1
                continue
            if await store_reading(session, district.id, reading) is not None:
                stored += 1
            await cache_reading(
                ctx.redis, district.id, reading, ttl_minutes=settings.reading_ttl_minutes, now=now
            )
            should_alert = update_alert_state(
                district,
                reading.aqi,
                threshold=settings.alert_threshold,
                clear_threshold=settings.alert_clear_threshold,
                repeat_hours=settings.alert_repeat_hours,
                now=now,
            )
            if should_alert:
                alerts.append((district.id, reading.aqi, reading.pm2_5))
        await session.commit()

    # Xabarlar holat saqlangandan keyin yuboriladi
    for district_id, aqi, pm2_5 in alerts:
        _dispatch_alert(settings, district_id, aqi, pm2_5)

    log.info("Havo yangilandi: %d saqlandi, %d xato, %d ogohlantirish", stored, failed, len(alerts))
    return {"stored": stored, "failed": failed, "alerts": len(alerts)}
