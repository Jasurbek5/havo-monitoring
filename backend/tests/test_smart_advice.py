import pytest
from app.services.smart_advice import generate_smart_advice


def test_smart_advice_clothing():
    # Cold test
    res = generate_smart_advice(aqi=30, temp=-5.0, feels_like=-7.0, lang="uz")
    assert "palto" in res["items"][0]["text"]

    # Warm test
    res2 = generate_smart_advice(aqi=30, temp=22.0, feels_like=22.0, lang="uz")
    assert "qulay" in res2["items"][0]["text"]


def test_smart_advice_outdoors():
    # Rain test
    res = generate_smart_advice(aqi=40, temp=15.0, feels_like=15.0, weather_code=61, lang="uz")
    assert "soyabon" in res["items"][1]["text"]

    # High wind test
    res2 = generate_smart_advice(aqi=40, temp=15.0, feels_like=15.0, weather_code=0, wind_speed=11.0, lang="uz")
    assert "shamol" in res2["items"][1]["text"]


def test_smart_advice_health():
    # High AQI
    res = generate_smart_advice(aqi=160, temp=20.0, feels_like=20.0, lang="uz")
    assert "niqob" in res["items"][2]["text"]

    # Clean AQI
    res2 = generate_smart_advice(aqi=25, temp=20.0, feels_like=20.0, lang="uz")
    assert "toza" in res2["items"][2]["text"]

