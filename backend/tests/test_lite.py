"""Yengil rejim (Docker, PostgreSQL, Redis va Celery'siz): kesh, jadval, baza va ilovaning ishga tushishi."""

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.main import app
from app.config import Settings, get_settings
from app.core.memory_cache import MemoryCache
from app.db.lite import init_lite_db
from app.db.session import dispose_engine, make_engine
from app.models import District, User
from app.tasks import air_quality as air_tasks
from app.tasks import background
from app.tasks.lite import next_daily_run
from tests.test_tasks import _add_user, task_env  # noqa: F401  (fixture)

TASHKENT = ZoneInfo("Asia/Tashkent")


# --- Xotiradagi kesh ---------------------------------------------------------


async def test_memory_cache_get_set_and_expiry():
    now = [100.0]
    cache = MemoryCache(clock=lambda: now[0])

    assert await cache.get("k") is None
    await cache.set("k", "v", ex=60)
    await cache.set("forever", "x")
    assert await cache.get("k") == "v"

    now[0] = 159.9
    assert await cache.get("k") == "v"
    now[0] = 160.0  # muddati tugadi
    assert await cache.get("k") is None
    assert await cache.get("forever") == "x"
    assert await cache.ping() is True


# --- Jadval ------------------------------------------------------------------


def test_next_daily_run_before_and_after_the_hour():
    # Toshkent UTC+5: 06:30 mahalliy = 01:30 UTC
    before = datetime(2026, 10, 11, 1, 30, tzinfo=UTC)
    assert next_daily_run(before, 7, TASHKENT) == datetime(2026, 10, 11, 7, 0, tzinfo=TASHKENT)

    after = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)  # 08:00 mahalliy
    assert next_daily_run(after, 7, TASHKENT) == datetime(2026, 10, 12, 7, 0, tzinfo=TASHKENT)

    exactly = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)  # roppa-rosa 07:00: keyingisi ertaga
    assert next_daily_run(exactly, 7, TASHKENT) == datetime(2026, 10, 12, 7, 0, tzinfo=TASHKENT)
    assert next_daily_run(exactly, 7, TASHKENT) - exactly == timedelta(hours=24)


async def test_spawn_runs_task_and_logs_errors_without_raising(caplog):
    done = []

    async def ok():
        done.append(1)

    async def boom():
        raise RuntimeError("kutilmagan")

    with caplog.at_level(logging.ERROR):
        await asyncio.gather(background.spawn(ok(), name="ok"), background.spawn(boom(), name="boom"))
    assert done == [1]
    assert "boom" in caplog.text
    assert not background._running  # tugagan vazifalar ro'yxatdan chiqadi


# --- Ogohlantirish yuborish usuli -------------------------------------------


async def test_dispatch_alert_uses_background_task_in_lite_and_celery_otherwise(monkeypatch):
    calls: list[tuple] = []

    async def fake_send(district_id, aqi, pm2_5):
        calls.append(("lite", district_id, aqi, pm2_5))

    queued: list[tuple] = []
    monkeypatch.setattr(air_tasks, "_send_district_alert", fake_send)
    monkeypatch.setattr(
        air_tasks, "send_district_alert", type("T", (), {"delay": lambda *a: queued.append(a[1:])})()
    )

    air_tasks._dispatch_alert(Settings(lite_mode=True), 7, 168, 80.0)
    await asyncio.gather(*background._running)
    assert calls == [("lite", 7, 168, 80.0)] and queued == []

    air_tasks._dispatch_alert(Settings(lite_mode=False), 8, 170, None)
    assert queued == [(8, 170, None)] and len(calls) == 1


async def test_lite_fetch_all_sends_alert_in_process_without_celery(task_env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("LITE_MODE", "true")
    get_settings.cache_clear()
    await _add_user(task_env.factory, 1, "chilonzor")
    task_env.provider.reading = task_env.provider.reading.__class__(
        aqi=168,
        pm2_5=80.0,
        pm10=90.0,
        recorded_at=task_env.provider.reading.recorded_at,
        source="fake",
    )

    result = await air_tasks._fetch_all()
    await asyncio.gather(*background._running)

    assert result["alerts"] == 12
    assert task_env.queued == []  # Celery'ga hech narsa ketmadi
    sent = [m for m in task_env.fake.requests if getattr(m, "chat_id", None) == 1]
    assert len(sent) == 1 and "168" in sent[0].text


# --- Baza --------------------------------------------------------------------


async def test_init_lite_db_creates_tables_and_seeds_idempotently(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'lite.db'}")
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await init_lite_db(engine, factory)
        await init_lite_db(engine, factory)  # ikkinchi marta: dublikat yo'q
        async with factory() as s:
            assert await s.scalar(select(func.count()).select_from(District)) == 25
            assert await s.scalar(select(func.count()).select_from(User)) == 0
    finally:
        await engine.dispose()


async def test_sqlite_file_engine_uses_wal_and_foreign_keys(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'wal.db'}")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
    finally:
        await engine.dispose()


# --- Ilovaning ishga tushishi ------------------------------------------------


def test_app_starts_in_lite_mode_with_only_sqlite(tmp_path, monkeypatch, provider):
    db_file = tmp_path / "havo.db"
    monkeypatch.setenv("LITE_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("BOT_TOKEN", "")
    # Jadvalning birinchi so'rovi 5 soniyadan keyin; test undan oldin tugaydi, tarmoqqa chiqmaydi
    monkeypatch.setattr("app.api.main.build_provider", lambda settings: provider)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            ready = client.get("/health/ready")
            assert ready.status_code == 200
            assert ready.json() == {"database": "ok", "cache": "ok"}
            assert client.get("/health").json() == {"status": "ok"}
            # Admin panel himoyalangan: parolsiz 401 qaytaradi
            assert client.get("/admin").status_code == 401
            assert client.get("/admin", auth=("wrong", "badpass")).status_code == 401

            # To'g'ri login/parol bilan kirish:
            admin_resp = client.get("/admin", auth=("admin", "admin123"))
            assert admin_resp.status_code == 200
            assert "Havo Monitoringi" in admin_resp.text
            api_resp = client.get("/admin/api/users", auth=("admin", "admin123"))
            assert api_resp.status_code == 200
            assert "total" in api_resp.json()
    finally:
        get_settings.cache_clear()
        asyncio.run(dispose_engine())

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("select count(*) from districts").fetchone() == (25,)
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"users", "districts", "complaints", "air_quality_logs", "admin_users"} <= tables
    assert provider.calls == 0


@pytest.mark.parametrize("lite", [True, False])
def test_settings_lite_flag_defaults_to_off(lite):
    assert Settings(lite_mode=lite).lite_mode is lite
    assert Settings().lite_mode is False
