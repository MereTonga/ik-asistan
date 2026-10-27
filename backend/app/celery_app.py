from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ik_asistan",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_tasks", "app.tasks.email_tasks", "app.tasks.maintenance_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    # Worker çökerse (örn. OCR sırasında `docker compose restart`) görev kaybolmasın, yeniden teslim edilsin.
    # Görevler idempotent: belge işleme yeniden çalışabilir, onay satır kilidi + durum kontrolüyle korunur,
    # e-posta kontrolü Redis kilidi + Message-ID damgasıyla korunur.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # dakikalar süren bir OCR, arkasındaki görevleri rezerve edip bekletmesin
    task_soft_time_limit=settings.TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=settings.TASK_SOFT_TIME_LIMIT_SECONDS + 300,
)

celery_app.conf.beat_schedule = {
    "check-new-emails-periodically": {
        "task": "check_new_emails",
        "schedule": settings.EMAIL_POLL_INTERVAL_SECONDS,
    },
    "close-stale-threads-daily": {
        "task": "close_stale_threads",
        "schedule": crontab(hour=3, minute=30),
    },
}
