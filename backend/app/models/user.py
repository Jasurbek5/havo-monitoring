from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy import false as sa_false
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.district import District


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(2), default="uz", server_default="uz")

    # Foydalanuvchining GPS koordinatasi saqlanmaydi, faqat aniqlangan hudud.
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True
    )

    # Havo xavfli darajaga yetganda push-xabar (AQI > chegara)
    alert_enabled: Mapped[bool] = mapped_column(default=True, server_default=sa_true())
    # Har kuni ertalabki xabar (opt-in)
    daily_digest: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    # Bot bloklangan bo'lsa False; foydalanuvchi qaytib yozsa yana True bo'ladi.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa_true())

    district: Mapped[District | None] = relationship(lazy="joined")
