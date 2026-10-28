from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "havo",
    broker=settings.broker_url,
    include=["app.tasks.air_quality", "app.tasks.notifications"],
)

celery_app.conf.update(
    timezone=settings.timezone,
    enable_utc=True,
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Ommaviy xabar yuborish uzoq davom etishi mumkin; Redis'da qayta yetkazib berish
    # (visibility timeout) undan uzunroq bo'lishi kerak.
    broker_transport_options={"visibility_timeout": 6 * 3600},
    beat_schedule={
        "fetch-air-quality": {
            "task": "air.fetch_all",
            "schedule": settings.fetch_interval_minutes * 60.0,
        },
        "daily-digest": {
            "task": "notify.daily_digest",
            "schedule": crontab(minute=0),
        },
    },
)
