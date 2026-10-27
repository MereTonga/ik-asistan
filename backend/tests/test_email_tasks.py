from unittest.mock import patch

import pytest

from tests.fakes import FakeInbox, FakeRedis


def _fake_graph(answer="Sahte cevap", was_escalated=False):
    class FakeGraph:
        def invoke(self, state):
            return {**state, "answer": answer, "was_escalated": was_escalated}

    return FakeGraph()


def _unique_ids():
    """send_reply mock'u için her çağrıda farklı bir Message-ID (unique kısıt gerçek)."""
    counter = {"n": 0}

    def _next(*args, **kwargs):
        counter["n"] += 1
        return f"<bot{counter['n']}@ik>"

    return _next


def _mail(**overrides):
    data = {
        "message_id": "<real-1@testcompany.com>",
        "in_reply_to": None,
        "references": [],
        "from_address": "calisan@testcompany.com",
        "subject": "Izin sorusu",
        "body": "Izin hakkim ne zaman basliyor?",
    }
    data.update(overrides)
    return data


@pytest.fixture
def fake_redis(monkeypatch):
    import app.tasks.email_tasks as tasks_module

    fake = FakeRedis()
    monkeypatch.setattr(tasks_module, "redis_client", fake)
    return fake


# --- process_single_email ---------------------------------------------------------------

@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_with_send_email_false_never_calls_smtp(mock_build_graph, mock_send_reply, db_session, test_company):
    """Test paneli (simülasyon) yolu: SMTP'ye hiç gidilmemeli, kayıt yine de oluşmalı."""
    from app.tasks.email_tasks import process_single_email
    from app.models import Message

    mock_build_graph.return_value = _fake_graph()

    result = process_single_email(_mail(message_id="<sim-1@example.com>", from_address="biri@gmail.com"), db_session, company_override=test_company, send_email=False)

    assert result["status"] == "processed"
    mock_send_reply.assert_not_called()
    messages = db_session.query(Message).filter(Message.body.in_(["Izin hakkim ne zaman basliyor?", "Sahte cevap"])).all()
    assert len(messages) == 2
    outgoing = next(m for m in messages if m.sender_type == "ai_system")
    assert outgoing.message_id_header


@patch("app.tasks.email_tasks.send_reply", return_value="<reply-1@example.com>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_default_sends_reply_with_references(mock_build_graph, mock_send_reply, db_session, test_company):
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _fake_graph()

    result = process_single_email(_mail(references=["<r1@x>"]), db_session)

    assert result["status"] == "processed"
    mock_send_reply.assert_called_once()
    kwargs = mock_send_reply.call_args.kwargs
    assert kwargs["to_address"] == "calisan@testcompany.com"
    assert kwargs["in_reply_to_message_id"] == "<real-1@testcompany.com>"
    assert kwargs["references"] == ["<r1@x>"]


@patch("app.tasks.email_tasks.send_reply", return_value="<reply-2@example.com>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_escalation_marks_thread(mock_build_graph, mock_send_reply, db_session, test_company):
    from app.tasks.email_tasks import process_single_email
    from app.models import EmailThread

    mock_build_graph.return_value = _fake_graph(answer="İK'ya ilettim", was_escalated=True)

    result = process_single_email(_mail(message_id="<esc-1@x>"), db_session)

    assert result["was_escalated"] is True
    thread = db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<esc-1@x>").one()
    assert thread.status == "escalated"


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_is_idempotent(mock_build_graph, mock_send_reply, db_session, test_company):
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.return_value = "<reply-3@x>"

    first = process_single_email(_mail(message_id="<dup@x>"), db_session)
    second = process_single_email(_mail(message_id="<dup@x>"), db_session)

    assert first["status"] == "processed"
    assert second == {"status": "skipped", "reason": "already_processed"}
    assert mock_send_reply.call_count == 1


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_discards_stamp_when_reply_fails(mock_build_graph, mock_send_reply, db_session, test_company):
    """RAG ya da SMTP patlarsa gelen mesaj damgası silinir: mail bir sonraki poll'da yeniden denenir."""
    from app.tasks.email_tasks import process_single_email
    from app.models import EmailThread, Message

    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.side_effect = ConnectionError("SMTP kapalı")

    with pytest.raises(ConnectionError):
        process_single_email(_mail(message_id="<fail-1@x>"), db_session)

    assert db_session.query(Message).filter(Message.message_id_header == "<fail-1@x>").count() == 0
    assert db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<fail-1@x>").count() == 0

    # Düzelince aynı mail yeniden işlenebilir
    mock_send_reply.side_effect = None
    mock_send_reply.return_value = "<reply-4@x>"
    assert process_single_email(_mail(message_id="<fail-1@x>"), db_session)["status"] == "processed"


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_failure_keeps_existing_thread(mock_build_graph, mock_send_reply, db_session, test_company):
    """Var olan bir thread'e gelen mail patlarsa yalnızca o mesaj silinir, thread ve eski mesajlar kalır."""
    from app.tasks.email_tasks import process_single_email
    from app.models import EmailThread, Message

    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.return_value = "<reply-5@x>"
    process_single_email(_mail(message_id="<ok-1@x>", subject="Konu"), db_session)

    mock_send_reply.side_effect = ConnectionError("SMTP kapalı")
    with pytest.raises(ConnectionError):
        process_single_email(_mail(message_id="<ok-2@x>", in_reply_to="<reply-5@x>", subject="Re: Konu"), db_session)

    thread = db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<ok-1@x>").one()
    ids = {m.message_id_header for m in db_session.query(Message).filter(Message.thread_id == thread.id)}
    assert ids == {"<ok-1@x>", "<reply-5@x>"}


# --- hız sınırı ----------------------------------------------------------------------------

def test_rate_limit_counts_per_sender_per_hour(fake_redis, monkeypatch):
    import app.tasks.email_tasks as tasks_module

    monkeypatch.setattr(tasks_module.settings, "EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR", 2)

    assert tasks_module._rate_limit_exceeded("Ali@x.com") is False
    assert tasks_module._rate_limit_exceeded("ali@x.com") is False
    assert tasks_module._rate_limit_exceeded("ali@x.com") is True
    assert tasks_module._rate_limit_exceeded("baska@x.com") is False
    assert fake_redis.ttl[f"{tasks_module.RATE_KEY_PREFIX}ali@x.com"] == 3600


# --- check_new_emails_task (sahte gelen kutusu + sahte Redis) ---------------------------------

def _raw_mail(message_id, sender="calisan@testcompany.com", subject="Izin", body="Izin hakkim?", extra_headers=""):
    mid = f"Message-ID: {message_id}\r\n" if message_id else ""
    return (
        f"From: {sender}\r\nSubject: {subject}\r\n{mid}{extra_headers}Content-Type: text/plain; charset=utf-8\r\n\r\n{body}"
    ).encode("utf-8")


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_processes_marks_and_skips(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.tasks.email_tasks as tasks_module
    from app.models import Message

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    mock_build_graph.return_value = _fake_graph(was_escalated=False)
    mock_send_reply.side_effect = _unique_ids()

    # Daha önce işlenmiş ama işaretlenmemiş bir mail (DB'de kaydı var)
    from app.models import EmailThread
    old_thread = EmailThread(company_id=test_company.id, subject="Eski", employee_email="calisan@testcompany.com", root_message_id_header="<old@x>", status="open")
    db_session.add(old_thread)
    db_session.flush()
    db_session.add(Message(thread_id=old_thread.id, message_id_header="<old@x>", sender_type="employee", body="eski"))
    db_session.flush()

    inbox = FakeInbox({
        1: _raw_mail("<new@x>"),                                                   # işlenmeli → \Seen
        2: _raw_mail("<old@x>"),                                                   # zaten işlenmiş → sadece \Seen
        3: _raw_mail("<auto@x>", extra_headers="Auto-Submitted: auto-replied\r\n"),  # oto-yanıt → atla, hatırla
        4: _raw_mail("<unknown@x>", sender="biri@bilinmeyen.com"),                # bilinmeyen domain → atla, hatırla
        5: _raw_mail(None),                                                         # Message-ID yok → sentetik kimlikle işlenmeli
    })
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    result = tasks_module.check_new_emails_task()

    assert result == {"processed": 2, "skipped": 3, "errors": 0}
    assert inbox.marked == {1: False, 2: False, 5: False}
    assert inbox.full_fetches == [1, 5]  # atlananlar için gövde hiç indirilmedi
    assert fake_redis.exists(tasks_module._skip_key("<auto@x>"))
    assert fake_redis.exists(tasks_module._skip_key("<unknown@x>"))
    assert db_session.query(Message).filter(Message.message_id_header == "<imap-7-5@ik-asistan.local>").count() == 1
    assert fake_redis.locks == set()  # kilit serbest bırakıldı

    # İkinci poll: hatırlanan atlamalar gövde indirilmeden geçilir, işlenenler tekrar işlenmez
    inbox.full_fetches.clear()
    second = tasks_module.check_new_emails_task()
    assert second["processed"] == 0
    assert inbox.full_fetches == []
    assert mock_send_reply.call_count == 2


@patch("app.tasks.email_tasks.send_reply", return_value="<bot@ik>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_flags_escalated_mail(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.tasks.email_tasks as tasks_module

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    mock_build_graph.return_value = _fake_graph(answer="İK'ya ilettim", was_escalated=True)
    inbox = FakeInbox({9: _raw_mail("<esc@x>")})
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    tasks_module.check_new_emails_task()

    assert inbox.marked == {9: True}  # \Seen + \Flagged (yıldız)


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_rate_limits_sender(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.tasks.email_tasks as tasks_module

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(tasks_module.settings, "EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR", 2)
    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.side_effect = _unique_ids()
    inbox = FakeInbox({i: _raw_mail(f"<r{i}@x>") for i in range(1, 5)})
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    result = tasks_module.check_new_emails_task()

    assert result["processed"] == 2
    assert result["skipped"] == 2
    assert sorted(inbox.marked) == [1, 2]  # sınırı aşanlar okunmamış kaldı, sonra yeniden değerlendirilir


def test_check_new_emails_task_skips_when_lock_is_held(monkeypatch, fake_redis):
    import app.tasks.email_tasks as tasks_module

    fake_redis.locks.add(tasks_module.EMAIL_CHECK_LOCK_KEY)

    result = tasks_module.check_new_emails_task()

    assert result["skipped_run"] is True


@patch("app.tasks.email_tasks.send_reply", side_effect=ConnectionError("SMTP kapalı"))
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_isolates_per_mail_errors(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.tasks.email_tasks as tasks_module

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    mock_build_graph.return_value = _fake_graph()
    inbox = FakeInbox({1: _raw_mail("<e1@x>"), 2: _raw_mail("<e2@x>")})
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    result = tasks_module.check_new_emails_task()

    assert result == {"processed": 0, "skipped": 0, "errors": 2}
    assert inbox.marked == {}  # başarısız mailler okunmamış kalır, sonraki poll yeniden dener
    assert fake_redis.locks == set()


@patch("app.tasks.email_tasks.send_reply", return_value="<reply-9@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_persists_confidence_and_groundedness(mock_build_graph, mock_send_reply, db_session, test_company):
    from app.tasks.email_tasks import process_single_email
    from app.models import Message

    class Graph:
        def invoke(self, state):
            return {**state, "answer": "Cevap", "was_escalated": False, "max_similarity": 0.734, "is_grounded": True}

    mock_build_graph.return_value = Graph()

    process_single_email(_mail(message_id="<conf-1@x>"), db_session)

    outgoing = db_session.query(Message).filter(Message.message_id_header == "<reply-9@x>").one()
    assert outgoing.confidence_score == 0.734
    assert outgoing.is_grounded is True


# --- Faz 17.2: İK bildirimi ----------------------------------------------------

def _escalating_graph():
    class Graph:
        def invoke(self, state):
            return {**state, "answer": "İK'ya ilettim", "was_escalated": True, "has_confident_match": False, "max_similarity": 0.3}

    return Graph()


@patch("app.tasks.email_tasks.send_hr_notification")
@patch("app.tasks.email_tasks.send_reply", return_value="<r-n1@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_escalation_notifies_company_hr_address(mock_build_graph, mock_send_reply, mock_notify, db_session, test_company):
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _escalating_graph()
    test_company.hr_notify_email = "ik.muduru@testcompany.com"
    db_session.flush()

    process_single_email(_mail(message_id="<n1@x>", subject="Prim"), db_session)

    mock_notify.assert_called_once()
    kwargs = mock_notify.call_args.kwargs
    assert kwargs["hr_address"] == "ik.muduru@testcompany.com"
    assert kwargs["employee_address"] == "calisan@testcompany.com"
    assert "benzer içerik" in kwargs["reason"]


@patch("app.tasks.email_tasks.send_hr_notification")
@patch("app.tasks.email_tasks.send_reply", return_value="<r-n2@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_escalation_falls_back_to_global_setting(mock_build_graph, mock_send_reply, mock_notify, monkeypatch, db_session, test_company):
    import app.tasks.email_tasks as tasks_module
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _escalating_graph()
    monkeypatch.setattr(tasks_module.settings, "HR_NOTIFY_EMAIL", "ik-genel@sirket.com")

    process_single_email(_mail(message_id="<n2@x>"), db_session)

    assert mock_notify.call_args.kwargs["hr_address"] == "ik-genel@sirket.com"


@patch("app.tasks.email_tasks.send_hr_notification")
@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_no_notification_without_address_or_when_same_mailbox(mock_build_graph, mock_send_reply, mock_notify, monkeypatch, db_session, test_company):
    import app.tasks.email_tasks as tasks_module
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _escalating_graph()
    mock_send_reply.side_effect = _unique_ids()
    monkeypatch.setattr(tasks_module.settings, "HR_NOTIFY_EMAIL", None)
    process_single_email(_mail(message_id="<n3@x>"), db_session)
    mock_notify.assert_not_called()

    # Aynı kutu: bildirim kopya üretir, gönderilmez
    monkeypatch.setattr(tasks_module.settings, "EMAIL_ADDRESS", "ik@sirket.com")
    monkeypatch.setattr(tasks_module.settings, "HR_NOTIFY_EMAIL", "IK@sirket.com")
    process_single_email(_mail(message_id="<n4@x>"), db_session)
    mock_notify.assert_not_called()


@patch("app.tasks.email_tasks.send_hr_notification")
@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_no_notification_in_simulation_and_for_answered_mail(mock_build_graph, mock_send_reply, mock_notify, db_session, test_company):
    from app.tasks.email_tasks import process_single_email

    test_company.hr_notify_email = "ik.muduru@testcompany.com"
    db_session.flush()

    mock_build_graph.return_value = _escalating_graph()
    process_single_email(_mail(message_id="<n5@x>"), db_session, company_override=test_company, send_email=False)
    mock_notify.assert_not_called()

    mock_build_graph.return_value = _fake_graph(was_escalated=False)
    mock_send_reply.return_value = "<r-n6@x>"
    process_single_email(_mail(message_id="<n6@x>"), db_session)
    mock_notify.assert_not_called()


@patch("app.tasks.email_tasks.send_hr_notification", side_effect=ConnectionError("SMTP kapalı"))
@patch("app.tasks.email_tasks.send_reply", return_value="<r-n7@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_notification_failure_does_not_break_processing(mock_build_graph, mock_send_reply, mock_notify, db_session, test_company):
    from app.tasks.email_tasks import process_single_email
    from app.models import Message

    mock_build_graph.return_value = _escalating_graph()
    test_company.hr_notify_email = "ik.muduru@testcompany.com"
    db_session.flush()

    result = process_single_email(_mail(message_id="<n7@x>"), db_session)

    assert result["status"] == "processed"
    assert db_session.query(Message).filter(Message.message_id_header == "<r-n7@x>").count() == 1


# --- Faz 18.2: yetkili gönderen ve atlama belleği ------------------------------

def test_clear_skip_memory_removes_only_skip_keys(fake_redis):
    import app.tasks.email_tasks as tasks_module

    fake_redis.set(tasks_module._skip_key("<a@x>"), "unknown_domain")
    fake_redis.set(tasks_module._skip_key("<b@x>"), "auto")
    fake_redis.set(f"{tasks_module.RATE_KEY_PREFIX}ali@x.com", "3")

    assert tasks_module.clear_skip_memory() == 2
    assert not fake_redis.exists(tasks_module._skip_key("<a@x>"))
    assert fake_redis.exists(f"{tasks_module.RATE_KEY_PREFIX}ali@x.com")


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_accepts_authorized_personal_address(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.tasks.email_tasks as tasks_module
    from app.models import AuthorizedSender, EmailThread

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.side_effect = _unique_ids()
    db_session.add(AuthorizedSender(company_id=test_company.id, email="stajyer@gmail.com"))
    db_session.flush()

    inbox = FakeInbox({
        1: _raw_mail("<s1@x>", sender="Stajyer@gmail.com"),      # listede → çalışan gibi
        2: _raw_mail("<s2@x>", sender="yabanci@gmail.com"),      # listede değil, varsayılan şirket yok → atla
    })
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    result = tasks_module.check_new_emails_task()

    assert result == {"processed": 1, "skipped": 1, "errors": 0}
    assert inbox.marked == {1: False}
    db_session.expire_all()
    thread = db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<s1@x>").one()
    assert str(thread.company_id) == str(test_company.id)
    assert thread.is_external is False


# --- Faz 18.3: dış gönderenler ------------------------------------------------

@patch("app.tasks.email_tasks.send_reply", return_value="<r-ext1@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_external_sender_uses_public_scope_and_marks_thread(mock_build_graph, mock_send_reply, monkeypatch, db_session, test_company):
    import app.email_service.processor as processor_module
    from app.tasks.email_tasks import process_single_email
    from app.models import EmailThread

    seen_states = []

    class Graph:
        def invoke(self, state):
            seen_states.append(state)
            return {**state, "answer": "Genel cevap", "was_escalated": False}

    mock_build_graph.return_value = Graph()
    monkeypatch.setattr(processor_module.settings, "DEFAULT_COMPANY_DOMAIN", "testcompany.com")

    result = process_single_email(_mail(message_id="<ext1@x>", from_address="aday@outlook.com"), db_session)

    assert result["status"] == "processed"
    assert seen_states[0]["include_internal"] is False
    thread = db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<ext1@x>").one()
    assert thread.is_external is True
    assert str(thread.company_id) == str(test_company.id)


@patch("app.tasks.email_tasks.send_reply", return_value="<r-int1@x>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_employee_sender_keeps_internal_scope(mock_build_graph, mock_send_reply, monkeypatch, db_session, test_company):
    import app.email_service.processor as processor_module
    from app.tasks.email_tasks import process_single_email
    from app.models import EmailThread

    seen_states = []

    class Graph:
        def invoke(self, state):
            seen_states.append(state)
            return {**state, "answer": "İç cevap", "was_escalated": False}

    mock_build_graph.return_value = Graph()
    monkeypatch.setattr(processor_module.settings, "DEFAULT_COMPANY_DOMAIN", "testcompany.com")

    process_single_email(_mail(message_id="<int1@x>"), db_session)

    assert seen_states[0]["include_internal"] is True
    assert db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<int1@x>").one().is_external is False


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_check_new_emails_task_routes_unknown_sender_to_default_company(mock_build_graph, mock_send_reply, monkeypatch, fake_redis, db_session, test_session_factory, test_company):
    import app.email_service.processor as processor_module
    import app.tasks.email_tasks as tasks_module
    from app.models import EmailThread

    monkeypatch.setattr(tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(processor_module.settings, "DEFAULT_COMPANY_DOMAIN", "testcompany.com")
    mock_build_graph.return_value = _fake_graph()
    mock_send_reply.side_effect = _unique_ids()
    inbox = FakeInbox({1: _raw_mail("<d1@x>", sender="aday@outlook.com")})
    monkeypatch.setattr(tasks_module, "ImapInbox", lambda: inbox)

    result = tasks_module.check_new_emails_task()

    assert result["processed"] == 1
    assert inbox.marked == {1: False}
    assert not fake_redis.exists(tasks_module._skip_key("<d1@x>"))  # atlanmadı
    db_session.expire_all()
    assert db_session.query(EmailThread).filter(EmailThread.root_message_id_header == "<d1@x>").one().is_external is True


# --- Faz 19.1: konuşma hafızası -------------------------------------------------

def test_load_thread_history_returns_recent_turns_in_order_and_truncated(db_session, test_company, monkeypatch):
    import app.tasks.email_tasks as tasks_module
    from app.models import EmailThread, Message
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(tasks_module.settings, "THREAD_MEMORY_MESSAGES", 3)
    monkeypatch.setattr(tasks_module.settings, "THREAD_MEMORY_MAX_CHARS", 60)

    thread = EmailThread(company_id=test_company.id, subject="s", employee_email="c@testcompany.com", status="open")
    db_session.add(thread)
    db_session.flush()
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    bodies = [("employee", "ilk soru"), ("ai_system", "ilk cevap"), ("employee", "ikinci soru"), ("ai_system", "x" * 200)]
    for i, (sender_type, body) in enumerate(bodies):
        db_session.add(Message(thread_id=thread.id, message_id_header=f"<h{i}@x>", sender_type=sender_type, body=body, created_at=base + timedelta(minutes=i)))
    db_session.flush()

    history = tasks_module.load_thread_history(db_session, thread.id)

    assert [h["role"] for h in history] == ["assistant", "user", "assistant"]  # en eski ('ilk soru') düştü, kronolojik
    assert history[1]["content"] == "ikinci soru"
    assert history[2]["content"].endswith("…") and len(history[2]["content"]) == 61

    monkeypatch.setattr(tasks_module.settings, "THREAD_MEMORY_MESSAGES", 0)
    assert tasks_module.load_thread_history(db_session, thread.id) == []


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_follow_up_mail_gets_history_but_first_mail_does_not(mock_build_graph, mock_send_reply, db_session, test_company):
    from app.tasks.email_tasks import process_single_email

    seen_states = []

    class Graph:
        def invoke(self, state):
            seen_states.append(state)
            return {**state, "answer": f"cevap {len(seen_states)}", "was_escalated": False}

    mock_build_graph.return_value = Graph()
    mock_send_reply.side_effect = _unique_ids()

    process_single_email(_mail(message_id="<f1@x>", subject="Uzaktan çalışma", body="Haftada kaç gün ofis?"), db_session)
    process_single_email(_mail(message_id="<f2@x>", subject="Re: Uzaktan çalışma", body="Peki ya cuma günleri?"), db_session)

    assert seen_states[0]["history"] == []
    assert seen_states[1]["history"] == [
        {"role": "user", "content": "Haftada kaç gün ofis?"},
        {"role": "assistant", "content": "cevap 1"},
    ]
