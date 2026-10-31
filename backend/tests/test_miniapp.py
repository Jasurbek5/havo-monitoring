from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
import pytest

from app.api.main import app
import app.db.session as session_module


@pytest.mark.asyncio
async def test_miniapp_html_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/app")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "Havo & Ob-havo" in res.text
        assert "telegram-web-app.js" in res.text
        assert "aqiProgressCircle" in res.text
        assert "settingsBtn" in res.text
        assert "settingsModal" in res.text
        assert "weatherIconHero" in res.text
        assert "WeatherIcons" in res.text
        assert "AppIcons" in res.text
        assert "aqiGaugeCenterIcon" in res.text


@pytest.mark.asyncio
async def test_miniapp_districts_endpoint(seeded, session_factory):
    with patch.object(session_module, "_factory", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/miniapp/districts?lang=uz")
            assert res.status_code == 200
            data = res.json()
            assert "city" in data
            assert "regions" in data
            assert len(data["city"]) >= 12
            assert len(data["regions"]) >= 13


@pytest.mark.asyncio
async def test_miniapp_data_endpoint(seeded, session_factory):
    with patch.object(session_module, "_factory", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/miniapp/data?district_id=2&lang=uz")
            assert res.status_code == 200
            data = res.json()
            assert data["district"]["id"] == 2
            assert "Chilonzor" in data["district"]["name"]
            assert "aqi" in data["air"]
            assert "temp" in data["weather"]
            assert "hourly" in data
            assert "weekly" in data
            if data["hourly"]:
                assert "is_tomorrow" in data["hourly"][0]
                assert "weather_code" in data["hourly"][0]
            if data["weekly"]:
                assert "weather_code" in data["weekly"][0]


@pytest.mark.asyncio
async def test_miniapp_settings_endpoint(seeded, session_factory):
    with patch.object(session_module, "_factory", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Get default settings for non-existent user
            res = await client.get("/api/miniapp/settings?telegram_id=888888&lang=uz")
            assert res.status_code == 200
            data = res.json()
            assert data["telegram_id"] == 888888
            assert data["alert_enabled"] is True
            assert data["daily_digest"] is False

            # 2. Update settings via POST
            update_payload = {
                "telegram_id": 888888,
                "alert_enabled": False,
                "daily_digest": True,
                "digest_time": "08:00",
                "timezone": "Asia/Tashkent",
            }
            post_res = await client.post("/api/miniapp/settings?lang=uz", json=update_payload)
            assert post_res.status_code == 200
            post_data = post_res.json()
            assert post_data["ok"] is True
            assert post_data["settings"]["alert_enabled"] is False
            assert post_data["settings"]["daily_digest"] is True
            assert post_data["settings"]["digest_time"] == "08:00"

            # 3. Verify changes persist on GET
            get_res = await client.get("/api/miniapp/settings?telegram_id=888888&lang=uz")
            assert get_res.status_code == 200
            saved = get_res.json()
            assert saved["alert_enabled"] is False
            assert saved["daily_digest"] is True
            assert saved["digest_time"] == "08:00"


@pytest.mark.asyncio
async def test_miniapp_search_and_select_location(seeded, session_factory):
    with patch.object(session_module, "_factory", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Test global search endpoint
            with patch("app.api.miniapp.search_locations") as mock_search:
                from app.services.geocoding import LocationResult
                mock_search.return_value = [
                    LocationResult(
                        name_uz="Istanbul",
                        name_ru="Стамбул",
                        name_en="Istanbul",
                        lat=41.0082,
                        lon=28.9784,
                        country="Turkey",
                    )
                ]
                search_res = await client.get("/api/miniapp/search?q=Istanbul&lang=uz")
                assert search_res.status_code == 200
                items = search_res.json()
                assert len(items) == 1
                assert "Istanbul" in items[0]["name"]

            # 2. Test select-location endpoint
            select_payload = {
                "name_uz": "Istanbul",
                "name_ru": "Стамбул",
                "name_en": "Istanbul",
                "lat": 41.0082,
                "lon": 28.9784,
                "country": "Turkey",
                "telegram_id": 888888,
                "set_as_home": True,
            }
            sel_res = await client.post("/api/miniapp/select-location?lang=uz", json=select_payload)
            assert sel_res.status_code == 200
            sel_data = sel_res.json()
            assert sel_data["ok"] is True
            assert sel_data["district"]["id"] is not None
            assert "Istanbul" in sel_data["district"]["name"]
            assert sel_data["is_home"] is True
            assert sel_data["home_district_id"] == sel_data["district"]["id"]
