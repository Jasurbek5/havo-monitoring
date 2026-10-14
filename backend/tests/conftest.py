import os

# Testlar hech qachon haqiqiy Telegram, Redis yoki PostgreSQL'ga ulanmaydi.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("OWM_API_KEY", "test-key")
os.environ.setdefault("LITE_MODE", "false")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool, StaticPool  # noqa: E402

from app.db.seed import seed_districts  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.air_quality import AirReading, ProviderError  # noqa: E402


@pytest_asyncio.fixture
async def session_factory():
    """Odatda xotiradagi SQLite. TEST_DATABASE_URL berilsa (masalan, haqiqiy PostgreSQL),
    testlar o'sha bazada ishlaydi; u yerdagi jadvallar har testdan oldin qayta yaratiladi."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    else:
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    if url:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(session: AsyncSession) -> AsyncSession:
    await seed_districts(session)
    return session


class FakeProvider:
    """Haqiqiy API o'rniga: chaqiruvlarni sanaydi va kerak bo'lsa xato beradi."""

    name = "fake"

    def __init__(self, aqi: int = 132, pm2_5: float = 48.0, pm10: float = 71.0) -> None:
        self.calls = 0
        self.fail = False
        self.reading = AirReading(
            aqi=aqi,
            pm2_5=pm2_5,
            pm10=pm10,
            recorded_at=datetime(2026, 10, 10, 11, 30, tzinfo=UTC),
            source="fake",
        )

    async def fetch(self, lat: float, lon: float) -> AirReading:
        self.calls += 1
        if self.fail:
            raise ProviderError("fake xato")
        return self.reading

    async def aclose(self) -> None:
        pass


class FakeRedis:
    """Faqat get/set(ex=) kerak bo'ladigan oddiy kesh."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    async def aclose(self) -> None:
        pass


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
