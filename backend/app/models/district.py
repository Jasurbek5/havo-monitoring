import enum
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy import false as sa_false
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, str_enum


class DistrictKind(enum.StrEnum):
    CITY_DISTRICT = "city_district"  # Toshkent shahri tumani
    REGION = "region"  # viloyat markazi (sinov va kengayish uchun)


class District(CreatedAtMixin, Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name_uz: Mapped[str] = mapped_column(String(100))
    name_ru: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[DistrictKind] = mapped_column(
        str_enum(DistrictKind), default=DistrictKind.CITY_DISTRICT
    )
    # Tuman/hudud markazi (taxminiy). Havo ma'lumoti shu koordinata bo'yicha olinadi.
    lat: Mapped[float]
    lon: Mapped[float]

    # True bo'lsa ma'lumot Celery orqali har 30 daqiqada olinadi.
    # False bo'lsa (viloyatlar) faqat foydalanuvchi so'raganda olinib, keshlanadi.
    poll_enabled: Mapped[bool] = mapped_column(default=True, server_default=sa_true())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa_true())

    # Xavfli havo xabarini takror-takror yubormaslik uchun holat.
    alert_active: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def name(self, lang: str) -> str:
        if lang == "ru":
            return self.name_ru
        if lang == "en":
            return self.name_en or self.name_uz
        return self.name_uz

    def __repr__(self) -> str:  # pragma: no cover
        return f"<District {self.slug}>"
