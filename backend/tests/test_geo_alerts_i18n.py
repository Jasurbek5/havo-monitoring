from datetime import UTC, datetime, timedelta
from string import Formatter
from zoneinfo import ZoneInfo

import pytest

from app.core.geo import haversine_km, nearest
from app.core.i18n import DEFAULT_LANG, all_translations, t
from app.core.locales import en, ru, uz
from app.core.messages import format_air_message, format_alert_message, format_digest_message
from app.db.seed_data import DISTRICTS
from app.models import ComplaintCategory, District
from app.services.alerts import update_alert_state

# --- geo ---------------------------------------------------------------------


def test_haversine_tashkent_samarkand():
    km = haversine_km(41.311, 69.279, 39.654, 66.960)
    assert 260 < km < 280


def test_haversine_zero():
    assert haversine_km(41.3, 69.2, 41.3, 69.2) == pytest.approx(0)


def test_nearest_picks_closest_district():
    chilonzor = next(d for d in DISTRICTS if d.slug == "chilonzor")
    found = nearest(DISTRICTS, chilonzor.lat + 0.001, chilonzor.lon, max_km=100)
    assert found is not None and found[0].slug == "chilonzor"

    samarkand = next(d for d in DISTRICTS if d.slug == "samarqand")
    found = nearest(DISTRICTS, samarkand.lat, samarkand.lon + 0.05, max_km=100)
    assert found is not None and found[0].slug == "samarqand"


def test_nearest_respects_max_distance():
    assert nearest(DISTRICTS, 55.75, 37.62, max_km=100) is None  # Moskva
    assert nearest([], 41.3, 69.2) is None


def test_seed_data_is_consistent():
    slugs = [d.slug for d in DISTRICTS]
    assert len(slugs) == len(set(slugs))
    assert sum(d.kind.value == "city_district" for d in DISTRICTS) == 12
    assert sum(d.kind.value == "region" for d in DISTRICTS) == 13
    for d in DISTRICTS:
        assert 36 < d.lat < 46 and 55 < d.lon < 75  # O'zbekiston chegarasi ichida


# --- ogohlantirish holati ----------------------------------------------------

KW = {"threshold": 150, "clear_threshold": 130, "repeat_hours": 6}


def _district() -> District:
    return District(
        slug="x", name_uz="X", name_ru="Х", lat=41.0, lon=69.0, alert_active=False, last_alert_at=None
    )


def test_alert_sent_once_then_suppressed_then_repeated():
    d = _district()
    t0 = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)

    assert update_alert_state(d, 160, now=t0, **KW) is True
    assert d.alert_active is True

    assert update_alert_state(d, 170, now=t0 + timedelta(hours=1), **KW) is False
    assert update_alert_state(d, 170, now=t0 + timedelta(hours=5, minutes=59), **KW) is False
    assert update_alert_state(d, 170, now=t0 + timedelta(hours=6), **KW) is True


def test_alert_hysteresis_and_rearm():
    d = _district()
    t0 = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)
    update_alert_state(d, 160, now=t0, **KW)

    # 140: chegaradan past, lekin tozalash chegarasidan (130) yuqori: holat saqlanadi
    assert update_alert_state(d, 140, now=t0 + timedelta(hours=1), **KW) is False
    assert d.alert_active is True
    # shu holatda yana 155 ga chiqsa ham xabar yog'ib ketmaydi
    assert update_alert_state(d, 155, now=t0 + timedelta(hours=2), **KW) is False

    assert update_alert_state(d, 130, now=t0 + timedelta(hours=3), **KW) is False
    assert d.alert_active is False
    # tozalangach yangi ko'tarilish yana xabar beradi
    assert update_alert_state(d, 151, now=t0 + timedelta(hours=4), **KW) is True


def test_alert_threshold_is_strictly_greater():
    d = _district()
    assert update_alert_state(d, 150, now=datetime.now(UTC), **KW) is False
    assert update_alert_state(d, 151, now=datetime.now(UTC), **KW) is True


def test_alert_handles_naive_datetime_from_db():
    d = _district()
    d.alert_active = True
    d.last_alert_at = datetime(2026, 10, 10, 1, 0)  # SQLite tz'siz qaytaradi
    now = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)
    assert update_alert_state(d, 160, now=now, **KW) is True


# --- i18n --------------------------------------------------------------------


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def test_languages_have_same_keys():
    assert set(uz.TEXTS) == set(ru.TEXTS) == set(en.TEXTS)


def test_languages_have_same_placeholders():
    for key in uz.TEXTS:
        assert _placeholders(uz.TEXTS[key]) == _placeholders(ru.TEXTS[key]), key
        assert _placeholders(uz.TEXTS[key]) == _placeholders(en.TEXTS[key]), key


def test_every_category_and_level_has_texts():
    for category in ComplaintCategory:
        assert f"cat_{category.value}" in uz.TEXTS
    for level in ("good", "moderate", "unhealthy", "dangerous"):
        assert f"level_{level}" in uz.TEXTS and f"advice_{level}" in uz.TEXTS


def test_menu_button_texts_are_unique_across_languages():
    keys = [k for k in uz.TEXTS if k.startswith("btn_")]
    texts = [text for key in keys for text in all_translations(key)]
    assert len(texts) == len(set(texts))


def test_t_falls_back_to_default_language():
    assert t("xx", "btn_air") == t(DEFAULT_LANG, "btn_air")


# --- xabar matnlari ----------------------------------------------------------

TZ = ZoneInfo("Asia/Tashkent")
MEASURED = datetime(2026, 10, 10, 11, 30, tzinfo=UTC)


def test_air_message_content():
    text = format_air_message(
        "uz", "Chilonzor", aqi=132, pm2_5=48.0, pm10=71.0, recorded_at=MEASURED, tz=TZ
    )
    assert "Chilonzor" in text and "132" in text and "🟠" in text and "Zararli" in text
    assert "16:30" in text  # 11:30 UTC = 16:30 Toshkent
    assert "niqob" in text


def test_air_message_stale_and_missing_values():
    text = format_air_message(
        "ru", "Чиланзар", aqi=40, pm2_5=None, pm10=None, recorded_at=MEASURED, tz=TZ, stale=True
    )
    assert "🟢" in text and "—" in text and "последнее известное" in text


def test_alert_and_digest_messages():
    alert = format_alert_message("uz", "Sergeli", aqi=164, pm2_5=80.0)
    assert "Sergeli" in alert and "164" in alert and alert.startswith("🔴")
    digest = format_digest_message("ru", "Юнусабад", aqi=74)
    assert "Юнусабад" in digest and "74" in digest and "🟡" in digest


def test_english_messages_and_district_names():
    text = format_air_message(
        "en", "Chilanzar", aqi=45, pm2_5=8.5, pm10=20.0, recorded_at=MEASURED, tz=TZ
    )
    assert "Chilanzar" in text and "Good" in text and "🟢" in text

    alert = format_alert_message("en", "Sergeli", aqi=164, pm2_5=80.0)
    assert "Sergeli" in alert and "Alert" in alert and "Hazardous" in alert

    digest = format_digest_message("en", "Yunusabad", aqi=74)
    assert "Good morning" in digest and "Yunusabad" in digest and "Moderate" in digest

    d = District(
        slug="x",
        name_uz="Chilonzor",
        name_ru="Чиланзар",
        name_en="Chilanzar",
        lat=41.0,
        lon=69.0,
        alert_active=False,
        last_alert_at=None,
    )
    assert d.name("uz") == "Chilonzor"
    assert d.name("ru") == "Чиланзар"
    assert d.name("en") == "Chilanzar"

    d_no_en = District(
        slug="y",
        name_uz="Yunusobod",
        name_ru="Юнусабад",
        lat=41.0,
        lon=69.0,
        alert_active=False,
        last_alert_at=None,
    )
    assert d_no_en.name("en") == "Yunusobod"
