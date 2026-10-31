from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy import false as sa_false
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.district import District

if TYPE_CHECKING:
    from app.models.user_location import UserLocation


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(2), default="uz", server_default="uz")

    # Joriy tanlangan yoki aniqlangan hudud (boshqa joyga borganda o'zgaradi).
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Asosiy uy hududi: foydalanuvchi safarda bo'lsa ham ertalabki xabar va ogohlantirishlar
    # shu hudud bo'yicha yuboriladi.
    home_district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Havo xavfli darajaga yetganda push-xabar (AQI > chegara)
    alert_enabled: Mapped[bool] = mapped_column(default=True, server_default=sa_true())
    # Har kuni ertalabki xabar (opt-in)
    daily_digest: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    # Ertalabki xabar vaqti (masalan "07:00", "08:00")
    digest_time: Mapped[str] = mapped_column(
        String(5), default="07:00", server_default="07:00"
    )
    # Vaqt mintaqasi ("auto" - hudud bo'yicha avtomatik, yoki "Asia/Tashkent", "Asia/Tokyo", va h.k.)
    timezone: Mapped[str] = mapped_column(
        String(32), default="auto", server_default="auto"
    )
    # Bot bloklangan bo'lsa False; foydalanuvchi qaytib yozsa yana True bo'ladi.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa_true())

    district: Mapped[District | None] = relationship(
        foreign_keys=[district_id], lazy="joined"
    )
    home_district: Mapped[District | None] = relationship(
        foreign_keys=[home_district_id], lazy="joined"
    )
    saved_locations: Mapped[list["UserLocation"]] = relationship(
        "UserLocation",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UserLocation.order",
    )
