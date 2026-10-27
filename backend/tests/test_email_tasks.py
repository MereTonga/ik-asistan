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
