import pytest

from app.core.aqi import (
    AQILevel,
    aqi_from_pm10,
    aqi_from_pm25,
    calc_aqi,
    level_for,
)


@pytest.mark.parametrize(
    ("pm", "expected"),
    [
        (0, 0),
        (9.0, 50),
        (9.1, 51),
        (35.4, 100),
        (35.5, 101),
        (48.0, 132),
        (55.4, 150),
        (55.5, 151),
        (80.0, 168),
        (125.4, 200),
        (125.5, 201),
        (225.4, 300),
        (225.5, 301),
        (325.4, 500),
        (999, 500),  # jadvaldan tashqari: 500 bilan cheklanadi
        (-3, 0),  # manfiy sensor qiymati
    ],
)
def test_pm25(pm, expected):
    assert aqi_from_pm25(pm) == expected


@pytest.mark.parametrize(
    ("pm", "expected"),
    [
        (0, 0),
        (54, 50),
        (55, 51),
        (154, 100),
        (155, 101),
        (254, 150),
        (255, 151),
        (354, 200),
        (355, 201),
        (424, 300),
        (425, 301),
        (504, 400),
        (505, 401),
        (604, 500),
        (900, 500),
    ],
)
def test_pm10(pm, expected):
    assert aqi_from_pm10(pm) == expected


def test_concentration_is_truncated_not_rounded():
    # EPA qoidasi: PM2.5 0.1 gacha, PM10 butungacha KESILADI
    assert aqi_from_pm25(9.09) == 50
    assert aqi_from_pm10(54.9) == 50


def test_aqi_is_monotonic():
    values = [aqi_from_pm25(x / 10) for x in range(0, 4000)]
    assert values == sorted(values)
    values = [aqi_from_pm10(x) for x in range(0, 700)]
    assert values == sorted(values)


def test_calc_aqi_takes_worst_pollutant():
    assert calc_aqi(48.0, 71.0) == 132  # PM2.5 (132) PM10 (59) dan yomon
    assert calc_aqi(5.0, 400.0) == aqi_from_pm10(400.0)


def test_calc_aqi_with_single_pollutant():
    assert calc_aqi(48.0, None) == 132
    assert calc_aqi(None, 71.0) == 59


def test_calc_aqi_requires_a_value():
    with pytest.raises(ValueError):
        calc_aqi(None, None)


@pytest.mark.parametrize(
    ("aqi", "level"),
    [
        (0, AQILevel.GOOD),
        (50, AQILevel.GOOD),
        (51, AQILevel.MODERATE),
        (100, AQILevel.MODERATE),
        (101, AQILevel.UNHEALTHY),
        (150, AQILevel.UNHEALTHY),
        (151, AQILevel.DANGEROUS),
        (500, AQILevel.DANGEROUS),
    ],
)
def test_level_boundaries(aqi, level):
    assert level_for(aqi) is level
