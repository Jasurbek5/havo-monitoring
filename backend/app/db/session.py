"""Async engine va sessiya fabrikalari."""

import re
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None

SQLITE_BUSY_TIMEOUT_SECONDS = 30


def _tune_sqlite(engine: AsyncEngine) -> None:
    """Fayl asosidagi SQLite: bot va jadval bir vaqtda yozganda "database is locked" bo'lmasligi uchun
    WAL rejimi; tashqi kalitlar (PostgreSQL'dagidek) tekshiriladi."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def normalize_database_url(url: str) -> str:
    """PostgreSQL URL'larini asyncpg formatiga moslashtirish (Neon, Supabase, Render)."""
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    if "asyncpg" in url:
        # asyncpg 'channel_binding' parametrini tanimaydi, 'sslmode' o'rniga 'ssl' ishlatadi
        url = re.sub(r"[?&]channel_binding=[^&]+", "", url)
        url = re.sub(r"([?&])sslmode=require", r"\1ssl=require", url)
        url = url.replace("?&", "?").rstrip("?")
    return url


def make_engine(url: str, *, null_pool: bool = False) -> AsyncEngine:
    url = normalize_database_url(url)
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    if null_pool:
        kwargs["poolclass"] = NullPool
    elif not is_sqlite:
        kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
    if is_sqlite:
        kwargs["connect_args"] = {"timeout": SQLITE_BUSY_TIMEOUT_SECONDS}
    engine = create_async_engine(url, **kwargs)
    if is_sqlite and ":memory:" not in url and url != "sqlite+aiosqlite://":
        _tune_sqlite(engine)
    return engine


def get_engine() -> AsyncEngine:
    """Bot va API uchun umumiy engine (bitta event loop ichida yashaydi)."""
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _factory


def make_task_session_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Celery vazifalari uchun: har bir asyncio.run() o'z engine'ini oladi.

    asyncpg ulanishlari event loop'ga bog'langan, shuning uchun umumiy poolni
    turli loop'larda ishlatib bo'lmaydi. NullPool bu muammoni yo'qotadi.
    """
    engine = make_engine(get_settings().database_url, null_pool=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
