from typing import TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.district import District

if TYPE_CHECKING:
    from app.models.user import User


class UserLocation(CreatedAtMixin, Base):
    __tablename__ = "user_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), index=True)
    is_home: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    custom_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped["User"] = relationship(back_populates="saved_locations")
    district: Mapped[District] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserLocation user_id={self.user_id} district_id={self.district_id} is_home={self.is_home}>"

