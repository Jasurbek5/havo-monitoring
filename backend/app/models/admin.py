from sqlalchemy import String
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class AdminUser(CreatedAtMixin, Base):
    """Dashboard'ga kiruvchi adminlar (keyingi bosqichda JWT login shu jadvalga tayanadi)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa_true())
