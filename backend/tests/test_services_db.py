from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.seed import seed_districts
from app.db.seed_data import DISTRICTS
from app.models import (
    AirQualityLog,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    District,
    DistrictKind,
    User,
)
from app.services.air_quality import (
    AirReading,
    CurrentReading,
    ProviderError,
    cache_reading,
    get_current_reading,
    latest_log,
    store_reading,
)
from app.services.complaints import count_recent, create_complaint
from app.services.districts import list_districts, nearest_district

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


async def _district(session, slug="chilonzor") -> District:
    return await session.scalar(select(District).where(District.slug == slug))


# --- seed --------------------------------------------------------------------


async def test_seed_is_idempotent_and_polls_only_tashkent(session):
    created, updated = await seed_districts(session)
    assert (created, updated) == (len(DISTRICTS), 0)
    assert await seed_districts(session) == (0, 0)

    districts = (await session.scalars(select(District))).all()
    assert len(districts) == 25
    for d in districts:
        assert d.poll_enabled == (d.kind == DistrictKind.CITY_DISTRICT)
        assert d.is_active and not d.alert_active


async def test_seed_updates_coordinates_but_keeps_admin_flags(seeded):
    d = await _district(seeded)
    d.lat = 0.0
    d.is_active = True
    d.poll_enabled = False  # admin qo'lda o'chirgan
    await seeded.commit()

    assert await seed_districts(seeded) == (0, 1)
    d = await _district(seeded)
    assert d.lat != 0.0 and d.poll_enabled is False


async def test_list_and_nearest_district(seeded):
    city = await list_districts(seeded, DistrictKind.CITY_DISTRICT)
    assert len(city) == 12
    chilonzor = await _district(seeded)
    found = await nearest_district(seeded, chilonzor.lat, chilonzor.lon, 100)
    assert found is not None and found[0].slug == "chilonzor"
    assert await nearest_district(seeded, 55.75, 37.62, 100) is None


# --- modellar ----------------------------------------------------------------


async def test_user_defaults_and_unique_telegram_id(seeded):
    seeded.add(User(telegram_id=111))
    await seeded.commit()
    user = await seeded.scalar(select(User).where(User.telegram_id == 111))
    assert user.language == "uz" and user.alert_enabled is True
    assert user.daily_digest is False and user.is_active is True

    seeded.add(User(telegram_id=111))
    with pytest.raises(IntegrityError):
        await seeded.commit()


async def test_enums_are_stored_as_plain_values(seeded):
    seeded.add(User(telegram_id=1))
    await seeded.flush()
    user = await seeded.scalar(select(User))
    await create_complaint(
        seeded,
        user_id=user.id,
        district_id=None,
        category=ComplaintCategory.SMOKE_DUST,
        lat=41.3,
        lon=69.2,
        location_is_approx=True,
        text="tutun",
        photo_file_id=None,
        photo_path=None,
    )
    await seeded.commit()
    row = (await seeded.execute(text("SELECT category, status FROM complaints"))).one()
    assert tuple(row) == ("smoke_dust", "new")


async def test_count_recent_counts_only_last_24_hours(seeded):
    seeded.add(User(telegram_id=1))
    await seeded.flush()
    user = await seeded.scalar(select(User))

    def make(created_at):
        return Complaint(
            user_id=user.id,
            category=ComplaintCategory.OTHER,
            status=ComplaintStatus.NEW,
            lat=41.3,
            lon=69.2,
            text="x" * 10,
            created_at=created_at,
        )

    seeded.add_all(
        [make(NOW - timedelta(hours=1)), make(NOW - timedelta(hours=23)), make(NOW - timedelta(hours=25))]
    )
    await seeded.commit()
    assert await count_recent(seeded, user.id, now=NOW) == 2


# --- havo ma'lumoti: saqlash va kesh -----------------------------------------


async def test_store_reading_ignores_duplicates(seeded):
    d = await _district(seeded)
    reading = AirReading(aqi=90, pm2_5=30.0, pm10=50.0, recorded_at=NOW, source="t")
    assert await store_reading(seeded, d.id, reading) is not None
    assert await store_reading(seeded, d.id, reading) is None
    await seeded.commit()
    assert len((await seeded.scalars(select(AirQualityLog))).all()) == 1


async def test_get_current_reading_fetches_once_then_uses_db(seeded, provider):
    d = await _district(seeded)
    first = await get_current_reading(seeded, None, provider, d, now=NOW)
    assert (first.aqi, first.stale) == (132, False) and provider.calls == 1
    await seeded.commit()

    # Bazada yangi o'lchov bor: provayderga qayta murojaat qilinmaydi
    again = await get_current_reading(seeded, None, provider, d, now=NOW + timedelta(minutes=10))
    assert again.aqi == 132 and provider.calls == 1


async def test_get_current_reading_refetches_after_ttl(seeded, provider):
    d = await _district(seeded)
    await get_current_reading(seeded, None, provider, d, now=NOW)
    await seeded.commit()

    # created_at bazada haqiqiy "hozir"; TTL o'tganini ko'rsatish uchun vaqtni oldinga suramiz
    future = datetime.now(UTC) + timedelta(minutes=45)
    await get_current_reading(seeded, None, provider, d, now=future)
    assert provider.calls == 2


async def test_provider_failure_falls_back_to_stale_log(seeded, provider):
    d = await _district(seeded)
    seeded.add(
        AirQualityLog(
            district_id=d.id, aqi=77, pm2_5=20.0, pm10=40.0, source="t", recorded_at=NOW,
            created_at=NOW - timedelta(hours=3),
        )
    )
    await seeded.commit()
    provider.fail = True

    reading = await get_current_reading(seeded, None, provider, d, now=NOW)
    assert reading.aqi == 77 and reading.stale is True


async def test_provider_failure_without_history_raises(seeded, provider):
    d = await _district(seeded)
    provider.fail = True
    with pytest.raises(ProviderError):
        await get_current_reading(seeded, None, provider, d, now=NOW)


async def test_redis_cache_is_used_and_filled(seeded, provider, fake_redis):
    d = await _district(seeded)
    await get_current_reading(seeded, fake_redis, provider, d, now=NOW)
    assert f"aq:current:{d.id}" in fake_redis.data and provider.calls == 1

    again = await get_current_reading(seeded, fake_redis, provider, d, now=NOW)
    assert again.aqi == 132 and provider.calls == 1
    assert (await latest_log(seeded, d.id)) is not None


async def test_cache_reading_roundtrip(seeded, provider, fake_redis):
    d = await _district(seeded)
    await cache_reading(fake_redis, d.id, provider.reading, ttl_minutes=30, now=NOW)
    cached = CurrentReading.from_json(fake_redis.data[f"aq:current:{d.id}"])
    assert cached.aqi == 132 and cached.recorded_at == provider.reading.recorded_at
