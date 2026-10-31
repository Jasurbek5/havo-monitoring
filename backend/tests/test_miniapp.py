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
