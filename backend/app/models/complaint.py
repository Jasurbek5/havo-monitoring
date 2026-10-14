import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, str_enum
from app.models.district import District
from app.models.user import User


class ComplaintCategory(enum.StrEnum):
    BURNING = "burning"  # chiqindi / o't yoqish
    INDUSTRIAL = "industrial"  # sanoat chiqindisi
    SMOKE_DUST = "smoke_dust"  # tutun / chang
    TRANSPORT = "transport"
    TREE_CUTTING = "tree_cutting"  # daraxtlarni noqonuniy kesish
    OTHER = "other"


class ComplaintStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Complaint(CreatedAtMixin, Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Koordinatadan aniqlangan eng yaqin hudud (dashboard filtri uchun)
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[ComplaintCategory] = mapped_column(str_enum(ComplaintCategory))
    status: Mapped[ComplaintStatus] = mapped_column(
        str_enum(ComplaintStatus), default=ComplaintStatus.NEW, index=True
    )
    lat: Mapped[float]
    lon: Mapped[float]
    # True bo'lsa foydalanuvchi aniq nuqta yubormagan, hudud markazi olingan.
    location_is_approx: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    text: Mapped[str] = mapped_column(Text)
    # Telegram file_id va serverga yuklab olingan nusxa yo'li (dashboard shuni ko'rsatadi)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    photo_path: Mapped[str | None] = mapped_column(String(255))
    admin_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(lazy="joined")
    district: Mapped[District | None] = relationship(lazy="joined")
