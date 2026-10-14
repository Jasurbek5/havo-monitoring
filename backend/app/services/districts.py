from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import nearest
from app.models import District, DistrictKind


async def list_districts(
    session: AsyncSession, kind: DistrictKind | None = None
) -> list[District]:
    stmt = select(District).where(District.is_active.is_(True)).order_by(District.name_uz)
    if kind is not None:
        stmt = stmt.where(District.kind == kind)
    return list((await session.scalars(stmt)).all())


async def get_district(session: AsyncSession, district_id: int) -> District | None:
    return await session.get(District, district_id)


async def nearest_district(
    session: AsyncSession, lat: float, lon: float, max_km: float
) -> tuple[District, float] | None:
    """Koordinataga eng yaqin hudud markazi (masofa km da). `max_km` dan uzoq bo'lsa None.

    Bu markazgacha masofa bo'yicha taxminiy aniqlash; tuman chegarasi (poligon) hisobga olinmaydi.
    """
    return nearest(await list_districts(session), lat, lon, max_km)
