"""Koordinatalar bilan ishlash."""

import math
from collections.abc import Iterable
from typing import Protocol, TypeVar

EARTH_RADIUS_KM = 6371.0088


class HasCoords(Protocol):
    lat: float
    lon: float


T = TypeVar("T", bound=HasCoords)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ikki nuqta orasidagi masofa (km), katta doira bo'yicha."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest(
    items: Iterable[T], lat: float, lon: float, max_km: float | None = None
) -> tuple[T, float] | None:
    """Berilgan nuqtaga eng yaqin element va masofa. `max_km` dan uzoq bo'lsa None."""
    best: tuple[T, float] | None = None
    for item in items:
        distance = haversine_km(lat, lon, item.lat, item.lon)
        if best is None or distance < best[1]:
            best = (item, distance)
    if best is None or (max_km is not None and best[1] > max_km):
        return None
    return best
