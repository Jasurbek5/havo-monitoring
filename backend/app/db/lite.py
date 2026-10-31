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
        if engine.url.drivername.startswith("sqlite"):
            cols_result = await conn.execute(text("PRAGMA table_info(districts)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if cols and "name_en" not in cols:
                await conn.execute(text("ALTER TABLE districts ADD COLUMN name_en VARCHAR(100)"))
            if cols and "country" not in cols:
                await conn.execute(text("ALTER TABLE districts ADD COLUMN country VARCHAR(100)"))
            if cols and "admin_area" not in cols:
                await conn.execute(text("ALTER TABLE districts ADD COLUMN admin_area VARCHAR(100)"))

            user_cols_result = await conn.execute(text("PRAGMA table_info(users)"))
            user_cols = {row[1] for row in user_cols_result.fetchall()}
            if user_cols and "home_district_id" not in user_cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN home_district_id INTEGER REFERENCES districts(id)")
                )
            if user_cols and "digest_time" not in user_cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN digest_time VARCHAR(5) DEFAULT '07:00'")
                )
            if user_cols and "timezone" not in user_cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN timezone VARCHAR(32) DEFAULT 'auto'")
                )
        else:
            # PostgreSQL (Neon) ustunlarni xavfsiz qo'shish
            await conn.execute(text("ALTER TABLE districts ADD COLUMN IF NOT EXISTS name_en VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE districts ADD COLUMN IF NOT EXISTS country VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE districts ADD COLUMN IF NOT EXISTS admin_area VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS home_district_id INTEGER REFERENCES districts(id)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_time VARCHAR(5) DEFAULT '07:00'"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(32) DEFAULT 'auto'"))

    async with factory() as session:
        await seed_districts(session)
        # Eski avtomat Chilonzor biriktirilgan va birorta ham alohida saqlangan joyi bo'lmagan
        # foydalanuvchilarning joylashuvini tozalaymiz (NULL qilamiz), shunda birinchi kirganda qidiruv chiqadi
        chilonzor = await session.scalar(text("SELECT id FROM districts WHERE slug = 'chilonzor' LIMIT 1"))
        if chilonzor:
            await session.execute(
                text(
                    "UPDATE users SET district_id = NULL, home_district_id = NULL "
                    "WHERE district_id = :cid AND home_district_id = :cid "
                    "AND id NOT IN (SELECT DISTINCT user_id FROM user_locations)"
                ),
                {"cid": chilonzor},
            )
            await session.commit()
