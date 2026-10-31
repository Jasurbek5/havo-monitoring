from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import nearest
from app.models import District, DistrictKind, UserLocation
from app.services.geocoding import LocationResult


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
    """Koordinataga eng yaqin hudud markazi (masofa km da). `max_km` dan uzoq bo'lsa None."""
    return nearest(await list_districts(session), lat, lon, max_km)


async def get_or_create_district_by_location(
    session: AsyncSession,
    loc: LocationResult,
    *,
    max_snap_km: float = 3.0,
) -> District:
    """Koordinata yoki qidiruv natijasiga mos tuman/hududni oladi yoki yangi yaratadi.

    Agar 3 km ichida allaqachon mavjud tuman/shahar bo'lsa, o'shani qaytaradi.
    Aks holda yangi District yozuvi yaratadi (global qamrov uchun).
    """
    # 1. 3 km ichida mavjud hudud bormi?
    found = await nearest_district(session, loc.lat, loc.lon, max_km=max_snap_km)
    if found is not None:
        return found[0]

    # 2. Slug orqali tekshirish
    slug = f"loc-{round(loc.lat, 3)}-{round(loc.lon, 3)}"
    district = await session.scalar(select(District).where(District.slug == slug))
    if district is not None:
        return district

    # Faqat eng birinchi joylashuv nomini saqlaymiz (masalan: "Chilonzor", "Samarqand", "Istanbul")
    name_uz = (loc.name_uz or loc.display_name("uz").split(",")[0]).strip()[:100]
    name_ru = (loc.name_ru or loc.display_name("ru").split(",")[0]).strip()[:100]
    name_en = (loc.name_en or loc.display_name("en").split(",")[0]).strip()[:100]

    district = District(
        slug=slug,
        name_uz=name_uz,
        name_ru=name_ru,
        name_en=name_en,
        country=loc.country,
        admin_area=loc.admin_area,
        lat=loc.lat,
        lon=loc.lon,
        kind=DistrictKind.REGION,
        poll_enabled=False,
    )
    session.add(district)
    await session.commit()
    await session.refresh(district)
    return district


async def list_user_saved_locations(
    session: AsyncSession, user_id: int
) -> list[UserLocation]:
    stmt = (
        select(UserLocation)
        .where(UserLocation.user_id == user_id)
        .order_by(UserLocation.order.asc(), UserLocation.id.asc())
    )
    return list((await session.scalars(stmt)).all())


async def save_user_location(
    session: AsyncSession,
    user_id: int,
    district_id: int,
    *,
    is_home: bool = False,
    custom_name: str | None = None,
) -> UserLocation:
    """Foydalanuvchi uchun joylashuvni saqlaydi yoki yangilaydi."""
    existing = await session.scalar(
        select(UserLocation).where(
            UserLocation.user_id == user_id,
            UserLocation.district_id == district_id,
        )
    )
    saved = await list_user_saved_locations(session, user_id)
    if is_home:
        for s in saved:
            s.is_home = (s.district_id == district_id)

    if existing is not None:
        if is_home:
            existing.is_home = True
        if custom_name is not None:
            existing.custom_name = custom_name
        await session.commit()
        await session.refresh(existing)
        return existing

    loc_record = UserLocation(
        user_id=user_id,
        district_id=district_id,
        is_home=is_home,
        custom_name=custom_name,
        order=len(saved),
    )
    session.add(loc_record)
    await session.commit()
    await session.refresh(loc_record)
    return loc_record


async def remove_user_location(
    session: AsyncSession,
    user_id: int,
    district_id: int,
) -> bool:
    """Foydalanuvchining saqlangan joyini o'chiradi."""
    loc = await session.scalar(
        select(UserLocation).where(
            UserLocation.user_id == user_id,
            UserLocation.district_id == district_id,
        )
    )
    if loc is None:
        return False
    await session.delete(loc)
    await session.commit()
    return True
