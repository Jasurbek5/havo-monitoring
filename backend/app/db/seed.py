"""Hududlarni bazaga yozadi. Bir necha marta ishga tushirish xavfsiz (idempotent).

Ishga tushirish:  python -m app.db.seed
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_data import DISTRICTS
from app.db.session import dispose_engine, get_session_factory
from app.models import District, DistrictKind

log = logging.getLogger(__name__)


async def seed_districts(session: AsyncSession) -> tuple[int, int]:
    """Yangi hududlarni qo'shadi, mavjudlarning nom va koordinatasini yangilaydi.

    `poll_enabled` va `is_active` ga tegmaydi: admin ularni qo'lda o'zgartirgan bo'lishi mumkin.
    Qaytaradi: (qo'shildi, yangilandi).
    """
    existing = {d.slug: d for d in (await session.scalars(select(District))).all()}
    created = updated = 0
    for item in DISTRICTS:
        row = existing.get(item.slug)
        if row is None:
            session.add(
                District(
                    slug=item.slug,
                    name_uz=item.name_uz,
                    name_ru=item.name_ru,
                    name_en=item.name_en,
                    kind=item.kind,
                    lat=item.lat,
                    lon=item.lon,
                    # Faqat Toshkent tumanlari proaktiv yangilanadi
                    poll_enabled=item.kind == DistrictKind.CITY_DISTRICT,
                )
            )
            created += 1
        elif (row.name_uz, row.name_ru, row.name_en, row.lat, row.lon) != (
            item.name_uz,
            item.name_ru,
            item.name_en,
            item.lat,
            item.lon,
        ):
            row.name_uz, row.name_ru, row.name_en = item.name_uz, item.name_ru, item.name_en
            row.lat, row.lon = item.lat, item.lon
            updated += 1
    await session.commit()
    return created, updated


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with get_session_factory()() as session:
        created, updated = await seed_districts(session)
    await dispose_engine()
    log.info("Hududlar: %d ta qo'shildi, %d ta yangilandi", created, updated)


if __name__ == "__main__":
    asyncio.run(main())
