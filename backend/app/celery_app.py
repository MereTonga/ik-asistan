from celery import Celery

from app.config import settings

celery_app = Celery(
    "ik_asistan",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_tasks", "app.tasks.email_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "check-new-emails-periodically": {
        "task": "check_new_emails",
        "schedule": settings.EMAIL_POLL_INTERVAL_SECONDS,
    },
}
