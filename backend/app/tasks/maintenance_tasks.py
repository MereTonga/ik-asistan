from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.celery_app import celery_app
from app.config import settings
from app.db.session import SessionLocal
from app.logging_config import get_logger
from app.models import EmailThread, Message
from app.models.email import ThreadStatus

logger = get_logger(__name__)


def close_stale_threads(db, now: datetime | None = None) -> int:
    """Son mesajı THREAD_RESOLVE_AFTER_DAYS gündür olmayan 'open' thread'leri 'resolved' yapar.
    İdari bir kapanıştır (gerçek memnuniyet ölçümü değil); 'escalated' thread'lere dokunulmaz,
    onları İK takip eder. Kapatılan thread sayısını döner."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.THREAD_RESOLVE_AFTER_DAYS)

    last_message = (
        db.query(Message.thread_id.label("thread_id"), func.max(Message.created_at).label("last_at"))
        .group_by(Message.thread_id)
        .subquery()
    )
    stale_threads = (
        db.query(EmailThread)
        .join(last_message, last_message.c.thread_id == EmailThread.id)
        .filter(EmailThread.status == ThreadStatus.OPEN, last_message.c.last_at < cutoff)
        .all()
    )
    for thread in stale_threads:
        thread.status = ThreadStatus.RESOLVED
    db.commit()
    return len(stale_threads)


@celery_app.task(name="close_stale_threads", ignore_result=True)
def close_stale_threads_task():
    """Celery Beat: günde bir kez hareketsiz thread'leri kapatır."""
    db = SessionLocal()
    try:
        count = close_stale_threads(db)
        logger.info(f"close_stale_threads: {count} thread 'resolved' yapıldı")
        return {"resolved": count}
    finally:
        db.close()
