import asyncio
from datetime import datetime
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import func, or_, select

from app.bot.keyboards import air_kb
from app.core.messages import format_alert_message, format_digest_message
from app.models import District, User
from app.services.air_quality import ProviderError, get_current_reading
from app.services.messaging import send_many
from app.services.users import deactivate_users
from app.services.weather import get_current_weather
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

        # Ogohlantirish foydalanuvchining uy hududi (yoki agar uy belgilanmagan bo'lsa joriy hududi) bo'yicha yuboriladi
        users = (
            await session.scalars(
                select(User).where(
                    func.coalesce(User.home_district_id, User.district_id) == district_id,
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
def send_daily_digest(target_time: str | None = None) -> dict[str, int]:
    return asyncio.run(_send_daily_digest(target_time))


async def _send_daily_digest(target_time: str | None = None) -> dict[str, int]:
    async with task_context(need_bot=True) as ctx, ctx.session_factory() as session:
        if target_time is None:
            local_now = datetime.now(ctx.settings.tz)
            target_time = f"{local_now.hour:02d}:00"

        users = (
            await session.scalars(
                select(User).where(
                    User.daily_digest.is_(True),
                    User.is_active.is_(True),
                    or_(User.home_district_id.is_not(None), User.district_id.is_not(None)),
                    func.coalesce(User.digest_time, "07:00") == target_time,
                )
            )
        ).all()

        if not users:
            log.info("Ertalabki xabar (%s): yuboriladigan foydalanuvchilar yo'q", target_time)
            return {"sent": 0, "failed": 0, "blocked": 0}

        # Foydalanuvchilarni qabul qiluvchi hudud bo'yicha guruhlaymiz (home_district bo'lsa uy, aks holda joriy)
        by_district: dict[int, list[tuple[User, District]]] = defaultdict(list)
        for user in users:
            target_district = user.home_district or user.district
            if target_district is not None:
                by_district[target_district.id].append((user, target_district))

        messages: list[tuple[int, str, Any]] = []
        for district_id, group in by_district.items():
            district = group[0][1]
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

            weather = None
            try:
                weather = await get_current_weather(
                    ctx.redis, district, ctx.settings.owm_api_key, ttl_minutes=ctx.settings.reading_ttl_minutes
                )
            except Exception as exc:
                log.warning("%s: ertalabki xabarda ob-havo olinmadi: %s", district.slug, exc)

            for user, dist in group:
                switch_dist = None
                is_home = False
                other_name = None
                if user.home_district_id and user.district_id and user.home_district_id != user.district_id:
                    switch_dist = user.district
                    is_home = True
                    other_name = user.district.name(user.language)
                elif user.home_district_id:
                    is_home = True

                kb = air_kb(
                    user.language,
                    dist.id,
                    switch_district=switch_dist,
                    is_home=is_home,
                )
                text = format_digest_message(
                    user.language,
                    dist.name(user.language),
                    aqi=reading.aqi,
                    weather=weather,
                    is_home=is_home,
                    other_district_name=other_name,
                )
                messages.append((user.telegram_id, text, kb))

        await session.commit()  # get_current_reading yangi o'lchovlarni yozgan bo'lishi mumkin

        result = await send_many(ctx.bot, messages)
        await deactivate_users(session, result.blocked)
        await session.commit()

    log.info("Ertalabki xabar (%s): %d yuborildi, %d bloklagan", target_time, result.sent, len(result.blocked))
    return {"sent": result.sent, "failed": result.failed, "blocked": len(result.blocked)}
