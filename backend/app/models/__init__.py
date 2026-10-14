"""Barcha modellar shu yerda import qilinadi, shunda Alembic ularni ko'radi."""

from app.models.admin import AdminUser
from app.models.air_quality import AirQualityLog
from app.models.base import Base
from app.models.complaint import Complaint, ComplaintCategory, ComplaintStatus
from app.models.district import District, DistrictKind
from app.models.user import User

__all__ = [
    "AdminUser",
    "AirQualityLog",
    "Base",
    "Complaint",
    "ComplaintCategory",
    "ComplaintStatus",
    "District",
    "DistrictKind",
    "User",
]
