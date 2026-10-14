from collections.abc import Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def deactivate_users(session: AsyncSession, telegram_ids: Sequence[int]) -> None:
    """Botni bloklagan foydalanuvchilarga keyingi xabarlar yuborilmasligi uchun belgilaydi.

    Foydalanuvchi botga qayta yozsa, UserMiddleware uni yana faol qiladi.
    """
    if not telegram_ids:
        return
    await session.execute(
        update(User).where(User.telegram_id.in_(list(telegram_ids))).values(is_active=False)
    )
