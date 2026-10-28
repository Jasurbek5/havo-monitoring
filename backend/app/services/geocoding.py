"""Global geolokatsiya va qidiruv servisi (Reverse va Direct Geocoding).

Manbalar:
1. Reverse Geocoding: OpenWeatherMap Geo API (zaxira: BigDataCloud).
2. Qidiruv (Direct Geocoding): Open-Meteo Geocoding API (100% bepul, butun dunyo bo'ylab) va OWM Geo API.
"""

from dataclasses import dataclass
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

OWM_REVERSE_GEO_URL = "https://api.openweathermap.org/geo/1.0/reverse"
OWM_DIRECT_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"
OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
BIGDATACLOUD_REVERSE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"


@dataclass(frozen=True, slots=True)
class LocationResult:
    name_uz: str
    name_ru: str
    name_en: str
    lat: float
    lon: float
    country: str = ""
    admin_area: str = ""

    def display_name(self, lang: str = "uz") -> str:
        """Foydalanuvchiga ko'rsatish uchun chiroyli nom (masalan: 'Urgut, Samarqand')."""
        if lang == "ru":
            base = self.name_ru or self.name_uz
        elif lang == "en":
            base = self.name_en or self.name_uz
        else:
            base = self.name_uz or self.name_en or self.name_ru

        parts = [base]
        if self.admin_area and self.admin_area.lower() not in base.lower():
            parts.append(self.admin_area)
        if self.country and self.country.lower() not in (
            "uzbekistan",
            "o'zbekiston",
            "узбекистан",
            "uz",
        ):
            parts.append(self.country)
        return ", ".join(parts)


async def reverse_geocode_owm(
    lat: float, lon: float, api_key: str, *, client: httpx.AsyncClient | None = None
) -> LocationResult | None:
    if not api_key:
        return None
    owns = client is None
    c = client or httpx.AsyncClient(timeout=6.0)
    try:
        resp = await c.get(
            OWM_REVERSE_GEO_URL,
            params={"lat": lat, "lon": lon, "limit": 1, "appid": api_key},
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items or not isinstance(items, list):
            return None
        item = items[0]
        local = item.get("local_names", {})
        name_def = item.get("name", f"{lat:.2f}, {lon:.2f}")
        name_uz = local.get("uz") or name_def
        name_ru = local.get("ru") or name_def
        name_en = local.get("en") or name_def
        state = item.get("state", "")
        country = item.get("country", "")

        return LocationResult(
            name_uz=name_uz,
            name_ru=name_ru,
            name_en=name_en,
            lat=round(lat, 4),
            lon=round(lon, 4),
            country=country,
            admin_area=state,
        )
    except Exception as exc:
        log.warning("OWM reverse geocode xatosi: %r", exc)
        return None
    finally:
        if owns:
            await c.aclose()


async def reverse_geocode_bigdatacloud(
    lat: float, lon: float, lang: str = "uz", *, client: httpx.AsyncClient | None = None
) -> LocationResult:
    """Zaxira: BigDataCloud bepul xizmati orqali koordinatadan nomni topish."""
    owns = client is None
    c = client or httpx.AsyncClient(timeout=6.0)
    try:
        resp = await c.get(
            BIGDATACLOUD_REVERSE_URL,
            params={"latitude": lat, "longitude": lon, "localityLanguage": lang},
        )
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        data = resp.json()
        city = (
            data.get("locality")
            or data.get("city")
            or data.get("principalSubdivision")
            or f"Joylashuv ({lat:.2f}, {lon:.2f})"
        )
        admin = data.get("principalSubdivision", "")
        country = data.get("countryName", "")
        return LocationResult(
            name_uz=city,
            name_ru=city,
            name_en=city,
            lat=round(lat, 4),
            lon=round(lon, 4),
            country=country,
            admin_area=admin,
        )
    except Exception as exc:
        log.warning("BigDataCloud reverse geocode xatosi: %r", exc)
        coord_name = f"Joylashuv ({lat:.2f}, {lon:.2f})"
        return LocationResult(
            name_uz=coord_name,
            name_ru=coord_name,
            name_en=coord_name,
            lat=round(lat, 4),
            lon=round(lon, 4),
        )
    finally:
        if owns:
            await c.aclose()


async def reverse_geocode(
    lat: float, lon: float, owm_api_key: str = "", lang: str = "uz"
) -> LocationResult:
    """Koordinata bo'yicha shahar/tuman nomini aniqlash (OWM -> BigDataCloud)."""
    if owm_api_key:
        res = await reverse_geocode_owm(lat, lon, owm_api_key)
        if res:
            return res
    return await reverse_geocode_bigdatacloud(lat, lon, lang)


async def search_locations_open_meteo(
    query: str, limit: int = 5, *, client: httpx.AsyncClient | None = None
) -> list[LocationResult]:
    """Open-Meteo orqali shahar nomini qidirish (100% bepul, global)."""
    owns = client is None
    c = client or httpx.AsyncClient(timeout=7.0)
    try:
        resp = await c.get(
            OPEN_METEO_GEO_URL,
            params={"name": query, "count": limit, "language": "uz", "format": "json"},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("results")
        if not results:
            return []
        items: list[LocationResult] = []
        for r in results:
            name = r.get("name", query)
            admin = r.get("admin1", "")
            country = r.get("country", "")
            items.append(
                LocationResult(
                    name_uz=name,
                    name_ru=name,
                    name_en=name,
                    lat=round(float(r["latitude"]), 4),
                    lon=round(float(r["longitude"]), 4),
                    country=country,
                    admin_area=admin,
                )
            )
        return items
    except Exception as exc:
        log.warning("Open-Meteo qidiruvida xato (%s): %r", query, exc)
        return []
    finally:
        if owns:
            await c.aclose()


async def search_locations_owm(
    query: str, api_key: str, limit: int = 5, *, client: httpx.AsyncClient | None = None
) -> list[LocationResult]:
    """OpenWeatherMap orqali shahar nomini qidirish."""
    if not api_key:
        return []
    owns = client is None
    c = client or httpx.AsyncClient(timeout=7.0)
    try:
        resp = await c.get(
            OWM_DIRECT_GEO_URL,
            params={"q": query, "limit": limit, "appid": api_key},
        )
        if resp.status_code != 200:
            return []
        results = resp.json()
        if not results or not isinstance(results, list):
            return []
        items: list[LocationResult] = []
        for r in results:
            local = r.get("local_names", {})
            name_def = r.get("name", query)
            items.append(
                LocationResult(
                    name_uz=local.get("uz") or name_def,
                    name_ru=local.get("ru") or name_def,
                    name_en=local.get("en") or name_def,
                    lat=round(float(r["lat"]), 4),
                    lon=round(float(r["lon"]), 4),
                    country=r.get("country", ""),
                    admin_area=r.get("state", ""),
                )
            )
        return items
    except Exception as exc:
        log.warning("OWM qidiruvida xato (%s): %r", query, exc)
        return []
    finally:
        if owns:
            await c.aclose()


async def search_locations(
    query: str, owm_api_key: str = "", limit: int = 5
) -> list[LocationResult]:
    """Shahar yoki tuman nomini qidirish (Open-Meteo -> OWM)."""
    query = query.strip()
    if not query:
        return []
    # 1. Open-Meteo sinab ko'ramiz
    res = await search_locations_open_meteo(query, limit)
    if res:
        return res
    # 2. OWM sinab ko'ramiz
    if owm_api_key:
        res = await search_locations_owm(query, owm_api_key, limit)
        if res:
            return res
    return []
