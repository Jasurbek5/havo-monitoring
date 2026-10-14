from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class AirQualityLog(CreatedAtMixin, Base):
    """Bitta hudud uchun bitta o'lchov. Tarixiy grafik va dashboard shu jadvaldan olinadi."""

    __tablename__ = "air_quality_logs"
    # Bir xil o'lchovni ikki marta yozmaslik uchun. Bu indeks (district_id, recorded_at)
    # bo'yicha "oxirgi o'lchov" so'rovlarini ham tezlashtiradi.
    __table_args__ = (
        UniqueConstraint("district_id", "recorded_at", name="uq_air_quality_logs_district_recorded"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"))
    aqi: Mapped[int]
    pm2_5: Mapped[float | None]
    pm10: Mapped[float | None]
    source: Mapped[str] = mapped_column(String(32))
    # Provayder o'lchagan vaqt (UTC). created_at esa biz yozgan vaqt.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
