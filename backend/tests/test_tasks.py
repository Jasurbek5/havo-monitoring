"""Celery vazifalarining ichki (async) qismi: fayl asosidagi SQLite, soxta provayder va soxta bot."""

import types

import pytest_asyncio
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.seed import seed_districts
from app.models import AirQualityLog, Base, District, User
from app.tasks import air_quality as air_tasks
from app.tasks import notifications as notify_tasks
from app.tasks import runtime
from app.tasks.celery_app import celery_app
from tests.test_bot_flows import FakeSession


@pytest_asyncio.fixture
async def task_env(tmp_path, monkeypatch, provider, fake_redis):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST-TOKEN")
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await seed_districts(s)

    fake_session = FakeSession()
    monkeypatch.setattr(runtime, "build_provider", lambda settings: provider)
    monkeypatch.setattr(runtime, "Redis", types.SimpleNamespace(from_url=lambda url, **kw: fake_redis))
    monkeypatch.setattr(runtime, "create_bot", lambda settings: Bot(settings.bot_token, session=fake_session))

    queued: list[tuple] = []
    monkeypatch.setattr(
        air_tasks, "send_district_alert", types.SimpleNamespace(delay=lambda *args: queued.append(args))
    )

    yield types.SimpleNamespace(factory=factory, fake=fake_session, queued=queued, provider=provider)
    await engine.dispose()
    get_settings.cache_clear()


async def _logs(factory) -> list[AirQualityLog]:
    async with factory() as s:
        return list((await s.scalars(select(AirQualityLog))).all())


async def _add_user(factory, tg_id: int, slug: str, *, lang="uz", **flags) -> None:
    async with factory() as s:
        district = await s.scalar(select(District).where(District.slug == slug))
        s.add(User(telegram_id=tg_id, language=lang, district_id=district.id, **flags))
        await s.commit()


# --- air.fetch_all -----------------------------------------------------------


async def test_fetch_all_polls_only_tashkent_districts_and_dedupes(task_env):
    result = await air_tasks._fetch_all()
    assert result == {"stored": 12, "failed": 0, "alerts": 0}
    assert len(await _logs(task_env.factory)) == 12  # viloyatlar (poll_enabled=False) kirmaydi
    assert task_env.provider.calls == 12

    again = await air_tasks._fetch_all()  # provayder o'sha o'lchovni qaytaradi: dublikat yozilmaydi
    assert again["stored"] == 0
    assert len(await _logs(task_env.factory)) == 12


async def test_fetch_all_survives_provider_failure(task_env):
    task_env.provider.fail = True
    result = await air_tasks._fetch_all()
    assert result == {"stored": 0, "failed": 12, "alerts": 0}


async def test_fetch_all_queues_alert_once_for_dangerous_air(task_env):
    task_env.provider.reading = task_env.provider.reading.__class__(
        aqi=168,
        pm2_5=80.0,
        pm10=90.0,
        recorded_at=task_env.provider.reading.recorded_at,
        source="fake",
    )
    first = await air_tasks._fetch_all()
    assert first["alerts"] == 12 and len(task_env.queued) == 12
    assert task_env.queued[0][1:] == (168, 80.0)

    async with task_env.factory() as s:
        districts = (await s.scalars(select(District).where(District.poll_enabled.is_(True)))).all()
        assert all(d.alert_active and d.last_alert_at for d in districts)

    second = await air_tasks._fetch_all()  # havo yomon bo'lib turibdi: qayta xabar yo'q
    assert second["alerts"] == 0 and len(task_env.queued) == 12


# --- notify.district_alert ---------------------------------------------------


async def test_district_alert_goes_only_to_eligible_users(task_env):
    f = task_env.factory
    await _add_user(f, 1, "chilonzor", lang="uz")
    await _add_user(f, 2, "chilonzor", lang="ru")
    await _add_user(f, 3, "chilonzor", alert_enabled=False)
    await _add_user(f, 4, "chilonzor", is_active=False)
    await _add_user(f, 5, "sergeli")
    async with f() as s:
        chilonzor = await s.scalar(select(District).where(District.slug == "chilonzor"))

    result = await notify_tasks._send_district_alert(chilonzor.id, 168, 80.0)
    assert result == {"sent": 2, "failed": 0, "blocked": 0}

    sent = {m.chat_id: m.text for m in task_env.fake.requests}
    assert set(sent) == {1, 2}
    assert "xavfli darajada" in sent[1] and "168" in sent[1]
    assert "опасный уровень" in sent[2] and "Чиланзар" in sent[2]


async def test_blocked_users_are_deactivated(task_env):
    f = task_env.factory
    await _add_user(f, 1, "chilonzor")
    await _add_user(f, 2, "chilonzor")
    task_env.fake.blocked_chats.add(2)
    async with f() as s:
        chilonzor = await s.scalar(select(District).where(District.slug == "chilonzor"))

    result = await notify_tasks._send_district_alert(chilonzor.id, 168, 80.0)
    assert result == {"sent": 1, "failed": 0, "blocked": 1}
    async with f() as s:
        active = {u.telegram_id: u.is_active for u in (await s.scalars(select(User))).all()}
    assert active == {1: True, 2: False}


# --- notify.daily_digest -----------------------------------------------------


async def test_daily_digest_is_opt_in_and_localized(task_env):
    f = task_env.factory
    await _add_user(f, 1, "chilonzor", lang="uz", daily_digest=True)
    await _add_user(f, 2, "yunusobod", lang="ru", daily_digest=True)
    await _add_user(f, 3, "chilonzor", daily_digest=False)  # yoqmagan
    await _add_user(f, 4, "chilonzor", daily_digest=True, is_active=False)

    result = await notify_tasks._send_daily_digest()
    assert result == {"sent": 2, "failed": 0, "blocked": 0}
    sent = {m.chat_id: m.text for m in task_env.fake.requests}
    assert set(sent) == {1, 2}
    assert "Xayrli tong" in sent[1] and "Доброе утро" in sent[2]
    assert task_env.provider.calls == 2  # har bir hudud uchun bitta so'rov


async def test_daily_digest_skips_district_when_data_unavailable(task_env):
    await _add_user(task_env.factory, 1, "chilonzor", daily_digest=True)
    task_env.provider.fail = True
    assert (await notify_tasks._send_daily_digest())["sent"] == 0


# --- Celery sozlamalari ------------------------------------------------------


def test_celery_registers_tasks_and_schedule():
    celery_app.loader.import_default_modules()
    assert {"air.fetch_all", "notify.district_alert", "notify.daily_digest"} <= set(celery_app.tasks)

    schedule = celery_app.conf.beat_schedule
    assert schedule["fetch-air-quality"]["task"] == "air.fetch_all"
    assert schedule["fetch-air-quality"]["schedule"] == 30 * 60.0
    assert schedule["daily-digest"]["task"] == "notify.daily_digest"
    assert celery_app.conf.timezone == "Asia/Tashkent"
