"""Ommaviy xabarlar: xavfli havo ogohlantirishi va ertalabki xabar."""

import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select

from app.core.messages import format_alert_message, format_digest_message
from app.models import District, User
from app.services.air_quality import ProviderError, get_current_reading
from app.services.messaging import send_many
from app.services.users import deactivate_users
from app.tasks.celery_app import celery_app
from app.tasks.runtime import task_context

log = logging.getLogger(__name__)


@celery_app.task(name="notify.district_alert")
def send_district_alert(district_id: int, aqi: int, pm2_5: float | None) -> dict[str, int]:
    return asyncio.run(_send_district_alert(district_id, aqi, pm2_5))


async def _send_district_alert(district_id: int, aqi: int, pm2_5: float | None) -> dict[str, int]:
    async with task_context(need_bot=True) as ctx, ctx.session_factory() as session:
        district = await session.get(District, district_id)
        if district is None:
            return {"sent": 0, "failed": 0, "blocked": 0}

        users = (
            await session.scalars(
                select(User).where(
                    User.district_id == district_id,
                    User.alert_enabled.is_(True),
                    User.is_active.is_(True),
                )
            )
        ).all()
        messages = [
            (
                user.telegram_id,
                format_alert_message(user.language, district.name(user.language), aqi=aqi, pm2_5=pm2_5),
            )
            for user in users
        ]
        result = await send_many(ctx.bot, messages)
        await deactivate_users(session, result.blocked)
        await session.commit()

    log.info(
        "Ogohlantirish (%s, AQI %s): %d yuborildi, %d bloklagan, %d xato",
        district.slug,
        aqi,
        result.sent,
        len(result.blocked),
        result.failed,
    )
    return {"sent": result.sent, "failed": result.failed, "blocked": len(result.blocked)}


@celery_app.task(name="notify.daily_digest")
def send_daily_digest() -> dict[str, int]:
    return asyncio.run(_send_daily_digest())


async def _send_daily_digest() -> dict[str, int]:
    async with task_context(need_bot=True) as ctx, ctx.session_factory() as session:
        users = (
            await session.scalars(
                select(User).where(
                    User.daily_digest.is_(True),
                    User.is_active.is_(True),
                    User.district_id.is_not(None),
                )
            )
        ).all()

        by_district: dict[int, list[User]] = defaultdict(list)
        for user in users:
            by_district[user.district_id].append(user)

        messages: list[tuple[int, str]] = []
        for group in by_district.values():
            district = group[0].district
            try:
                reading = await get_current_reading(
                    session,
                    ctx.redis,
                    ctx.provider,
                    district,
                    ttl_minutes=ctx.settings.reading_ttl_minutes,
                )
            except ProviderError as exc:
                log.warning("%s: ertalabki xabar o'tkazib yuborildi: %s", district.slug, exc)
                continue
            messages.extend(
                (
                    user.telegram_id,
                    format_digest_message(user.language, district.name(user.language), aqi=reading.aqi),
                )
                for user in group
            )
        await session.commit()  # get_current_reading yangi o'lchovlarni yozgan bo'lishi mumkin

        result = await send_many(ctx.bot, messages)
        await deactivate_users(session, result.blocked)
        await session.commit()

    log.info("Ertalabki xabar: %d yuborildi, %d bloklagan", result.sent, len(result.blocked))
    return {"sent": result.sent, "failed": result.failed, "blocked": len(result.blocked)}
