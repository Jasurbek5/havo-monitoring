"""Yengil rejimda bazani tayyorlash: jadvallarni yaratadi va hududlarni yozadi.

PostgreSQL'da buni Alembic va `python -m app.db.seed` qiladi; SQLite'da migratsiya shart emas.
Ikkalasi ham bir necha marta ishga tushirilsa xavfsiz.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.seed import seed_districts
from app.models import Base


async def init_lite_db(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        cols_result = await conn.execute(text("PRAGMA table_info(districts)"))
        cols = {row[1] for row in cols_result.fetchall()}
        if cols and "name_en" not in cols:
            await conn.execute(text("ALTER TABLE districts ADD COLUMN name_en VARCHAR(100)"))
    async with factory() as session:
        await seed_districts(session)
