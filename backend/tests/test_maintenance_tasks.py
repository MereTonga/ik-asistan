from datetime import datetime, timedelta, timezone

from app.models import EmailThread, Message
from app.models.email import ThreadStatus
from app.tasks.maintenance_tasks import close_stale_threads


def _thread_with_message(db_session, company, status, last_message_age_days, subject):
    thread = EmailThread(company_id=company.id, subject=subject, employee_email="calisan@testcompany.com", status=status)
    db_session.add(thread)
    db_session.flush()
    db_session.add(Message(
        thread_id=thread.id,
        message_id_header=f"<{subject}@x>",
        sender_type="employee",
        body="soru",
        created_at=datetime.now(timezone.utc) - timedelta(days=last_message_age_days),
    ))
    db_session.flush()
    return thread


def test_close_stale_threads_resolves_only_old_open_threads(db_session, test_company, monkeypatch):
    import app.tasks.maintenance_tasks as maintenance_module

    monkeypatch.setattr(maintenance_module.settings, "THREAD_RESOLVE_AFTER_DAYS", 14)

    stale_open = _thread_with_message(db_session, test_company, ThreadStatus.OPEN, 20, "eski-acik")
    fresh_open = _thread_with_message(db_session, test_company, ThreadStatus.OPEN, 3, "yeni-acik")
    stale_escalated = _thread_with_message(db_session, test_company, ThreadStatus.ESCALATED, 40, "eski-yonlendirilmis")

    resolved_count = close_stale_threads(db_session)

    assert resolved_count == 1
    db_session.refresh(stale_open)
    db_session.refresh(fresh_open)
    db_session.refresh(stale_escalated)
    assert stale_open.status == ThreadStatus.RESOLVED
    assert fresh_open.status == ThreadStatus.OPEN
    assert stale_escalated.status == ThreadStatus.ESCALATED  # İK takip eder, otomatik kapanmaz


def test_close_stale_threads_uses_latest_message_not_thread_creation(db_session, test_company, monkeypatch):
    """Thread eski açılmış ama yakın zamanda mesaj almışsa kapanmamalı."""
    import app.tasks.maintenance_tasks as maintenance_module

    monkeypatch.setattr(maintenance_module.settings, "THREAD_RESOLVE_AFTER_DAYS", 14)

    thread = EmailThread(
        company_id=test_company.id, subject="uzun-konusma", employee_email="calisan@testcompany.com",
        status=ThreadStatus.OPEN, created_at=datetime.now(timezone.utc) - timedelta(days=60),
    )
    db_session.add(thread)
    db_session.flush()
    db_session.add(Message(thread_id=thread.id, message_id_header="<old@x>", sender_type="employee", body="a", created_at=datetime.now(timezone.utc) - timedelta(days=50)))
    db_session.add(Message(thread_id=thread.id, message_id_header="<new@x>", sender_type="ai_system", body="b", created_at=datetime.now(timezone.utc) - timedelta(days=2)))
    db_session.flush()

    assert close_stale_threads(db_session) == 0
    db_session.refresh(thread)
    assert thread.status == ThreadStatus.OPEN


# --- Faz 16.4: veri saklama ----------------------------------------------------

def test_purge_old_threads_is_disabled_by_default(db_session, test_company, monkeypatch):
    import app.tasks.maintenance_tasks as maintenance_module
    from app.tasks.maintenance_tasks import purge_old_threads

    monkeypatch.setattr(maintenance_module.settings, "THREAD_RETENTION_DAYS", 0)
    _thread_with_message(db_session, test_company, ThreadStatus.RESOLVED, 400, "cok-eski")

    assert purge_old_threads(db_session) == 0
    assert db_session.query(EmailThread).count() == 1


def test_purge_old_threads_deletes_threads_and_messages_past_retention(db_session, test_company, monkeypatch):
    import app.tasks.maintenance_tasks as maintenance_module
    from app.tasks.maintenance_tasks import purge_old_threads

    monkeypatch.setattr(maintenance_module.settings, "THREAD_RETENTION_DAYS", 90)
    old = _thread_with_message(db_session, test_company, ThreadStatus.RESOLVED, 120, "eski")
    old_escalated = _thread_with_message(db_session, test_company, ThreadStatus.ESCALATED, 200, "eski-yonlendirilmis")
    recent = _thread_with_message(db_session, test_company, ThreadStatus.OPEN, 10, "yeni")
    old_ids = {old.id, old_escalated.id}

    purged = purge_old_threads(db_session)

    assert purged == 2
    remaining = {t.id for t in db_session.query(EmailThread)}
    assert remaining == {recent.id}
    assert db_session.query(Message).filter(Message.thread_id.in_(old_ids)).count() == 0
    assert db_session.query(Message).filter(Message.thread_id == recent.id).count() == 1
