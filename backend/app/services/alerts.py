"""Xavfli havo ogohlantirishi: qachon yuborish va qachon takrorlamaslik."""

from datetime import UTC, datetime, timedelta

from app.models import District


def update_alert_state(
    district: District,
    aqi: int,
    *,
    threshold: int,
    clear_threshold: int,
    repeat_hours: int,
    now: datetime | None = None,
) -> bool:
    """Hududning ogohlantirish holatini yangilaydi; xabar YUBORISH kerak bo'lsa True qaytaradi.

    - AQI chegaradan oshganda birinchi marta: xabar yuboriladi.
    - Havo yomon bo'lib turganda: `repeat_hours` o'tmaguncha qayta yuborilmaydi.
    - AQI `clear_threshold` ga tushganda holat tozalanadi (chegara atrofida tebranganda
      xabar yog'ib ketmasligi uchun "gisterezis").
    """
    now = now or datetime.now(UTC)

    if aqi > threshold:
        last = district.last_alert_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        due = (
            not district.alert_active
            or last is None
            or now - last >= timedelta(hours=repeat_hours)
        )
        if due:
            district.alert_active = True
            district.last_alert_at = now
            return True
        return False

    if district.alert_active and aqi <= clear_threshold:
        district.alert_active = False
    return False
