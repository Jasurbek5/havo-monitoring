"""AQI hisoblash.

Formula va jadvallar: US EPA (PM2.5 uchun 2024 yil mayida yangilangan chegaralar, PM10 uchun
o'zgarmagan jadval). Kirish qiymatlari mkg/m3 (µg/m3).

Muhim: EPA rasmiy AQI'ni 24 soatlik o'rtacha (NowCast) bo'yicha hisoblaydi. Provayder esa
joriy soatlik qiymat beradi, shuning uchun bu yerdagi natija "joriy holat bahosi" bo'lib,
rasmiy AQI bilan farq qilishi mumkin.
"""

import enum
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

# (C_low, C_high, I_low, I_high)
_PM25_TABLE: list[tuple[str, str, int, int]] = [
    ("0.0", "9.0", 0, 50),
    ("9.1", "35.4", 51, 100),
    ("35.5", "55.4", 101, 150),
    ("55.5", "125.4", 151, 200),
    ("125.5", "225.4", 201, 300),
    ("225.5", "325.4", 301, 500),
]
_PM10_TABLE: list[tuple[str, str, int, int]] = [
    ("0", "54", 0, 50),
    ("55", "154", 51, 100),
    ("155", "254", 101, 150),
    ("255", "354", 151, 200),
    ("355", "424", 201, 300),
    ("425", "504", 301, 400),
    ("505", "604", 401, 500),
]


class AQILevel(enum.StrEnum):
    """Foydalanuvchiga ko'rsatiladigan 4 ta daraja."""

    GOOD = "good"  # 0-50
    MODERATE = "moderate"  # 51-100
    UNHEALTHY = "unhealthy"  # 101-150
    DANGEROUS = "dangerous"  # 151+


LEVEL_EMOJI: dict[AQILevel, str] = {
    AQILevel.GOOD: "🟢",
    AQILevel.MODERATE: "🟡",
    AQILevel.UNHEALTHY: "🟠",
    AQILevel.DANGEROUS: "🔴",
}


def _sub_index(concentration: float, table: list[tuple[str, str, int, int]], decimals: int) -> int:
    # EPA qoidasi: konsentratsiya yaxlitlanmaydi, kesiladi (PM2.5 0.1 gacha, PM10 butungacha).
    quantum = Decimal(1).scaleb(-decimals)
    c = max(Decimal(str(concentration)), Decimal(0)).quantize(quantum, rounding=ROUND_DOWN)

    last = table[-1]
    if c > Decimal(last[1]):
        return last[3]

    for c_low, c_high, i_low, i_high in table:
        if c <= Decimal(c_high):
            c_lo, c_hi = Decimal(c_low), Decimal(c_high)
            index = Decimal(i_high - i_low) / (c_hi - c_lo) * (c - c_lo) + i_low
            return int(index.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    raise AssertionError("unreachable")  # pragma: no cover


def aqi_from_pm25(pm2_5: float) -> int:
    return _sub_index(pm2_5, _PM25_TABLE, decimals=1)


def aqi_from_pm10(pm10: float) -> int:
    return _sub_index(pm10, _PM10_TABLE, decimals=0)


def calc_aqi(pm2_5: float | None, pm10: float | None) -> int:
    """Umumiy AQI = eng yomon ifloslantiruvchining indeksi."""
    values: list[int] = []
    if pm2_5 is not None:
        values.append(aqi_from_pm25(pm2_5))
    if pm10 is not None:
        values.append(aqi_from_pm10(pm10))
    if not values:
        raise ValueError("AQI hisoblash uchun kamida PM2.5 yoki PM10 kerak")
    return max(values)


def level_for(aqi: int) -> AQILevel:
    if aqi <= 50:
        return AQILevel.GOOD
    if aqi <= 100:
        return AQILevel.MODERATE
    if aqi <= 150:
        return AQILevel.UNHEALTHY
    return AQILevel.DANGEROUS
