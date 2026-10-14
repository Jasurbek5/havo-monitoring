import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Complaint, ComplaintCategory

log = logging.getLogger(__name__)


async def count_recent(
    session: AsyncSession, user_id: int, *, hours: int = 24, now: datetime | None = None
) -> int:
    """Foydalanuvchining oxirgi `hours` soatdagi murojaatlari soni (spamdan himoya)."""
    since = (now or datetime.now(UTC)) - timedelta(hours=hours)
    stmt = (
        select(func.count())
        .select_from(Complaint)
        .where(Complaint.user_id == user_id, Complaint.created_at >= since)
    )
    return int(await session.scalar(stmt) or 0)


async def create_complaint(
    session: AsyncSession,
    *,
    user_id: int,
    district_id: int | None,
    category: ComplaintCategory,
    lat: float,
    lon: float,
    location_is_approx: bool,
    text: str,
    photo_file_id: str | None,
    photo_path: str | None,
) -> Complaint:
    complaint = Complaint(
        user_id=user_id,
        district_id=district_id,
        category=category,
        lat=lat,
        lon=lon,
        location_is_approx=location_is_approx,
        text=text,
        photo_file_id=photo_file_id,
        photo_path=photo_path,
    )
    session.add(complaint)
    await session.flush()  # complaint.id shu yerda paydo bo'ladi
    return complaint


async def download_photo(bot: Bot, file_id: str, media_dir: str) -> str | None:
    """Rasmni serverga yuklab oladi va MEDIA_DIR ga nisbatan yo'lni qaytaradi.

    Telegram file_id'ning o'zi ham saqlanadi, shuning uchun yuklab olish muvaffaqiyatsiz
    bo'lsa murojaat baribir qabul qilinadi (None qaytadi).
    """
    relative = f"complaints/{uuid.uuid4().hex}.jpg"
    destination = Path(media_dir) / relative
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        await bot.download(file_id, destination=destination)
    except (TelegramAPIError, OSError) as exc:
        log.warning("Rasmni yuklab olib bo'lmadi: %r", exc)
        return None
    return relative
