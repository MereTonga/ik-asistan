from unittest.mock import patch


def _fake_graph(answer="Sahte cevap", was_escalated=False):
    class FakeGraph:
        def invoke(self, state):
            return {**state, "answer": answer, "was_escalated": was_escalated}

    return FakeGraph()


@patch("app.tasks.email_tasks.send_reply")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_with_send_email_false_never_calls_smtp(
    mock_build_graph, mock_send_reply, db_session, test_company
):
    """Test paneli (simülasyon) yolu: SMTP'ye hiç gidilmemeli, kayıt yine de oluşmalı."""
    from app.tasks.email_tasks import process_single_email
    from app.models import Message

    mock_build_graph.return_value = _fake_graph()

    email_data = {
        "message_id": "<sim-1@example.com>",
        "in_reply_to": None,
        "from_address": "biri@gmail.com",
        "subject": "Izin sorusu",
        "body": "Izin hakkim ne zaman basliyor?",
    }

    result = process_single_email(email_data, db_session, company_override=test_company, send_email=False)

    assert result["status"] == "processed"
    mock_send_reply.assert_not_called()

    # Gelen ve giden mesaj yine de kaydedilmiş olmalı (analitik için)
    messages = db_session.query(Message).filter(Message.body.in_(["Izin hakkim ne zaman basliyor?", "Sahte cevap"])).all()
    assert len(messages) == 2
    outgoing = next(m for m in messages if m.sender_type == "ai_system")
    assert outgoing.message_id_header  # simülasyonda da benzersiz bir Message-ID üretilir


@patch("app.tasks.email_tasks.send_reply", return_value="<reply-1@example.com>")
@patch("app.tasks.email_tasks.build_rag_graph")
def test_process_single_email_default_sends_reply(mock_build_graph, mock_send_reply, db_session, test_company):
    """Gerçek IMAP yolu (varsayılan): send_reply çağrılmalı."""
    from app.tasks.email_tasks import process_single_email

    mock_build_graph.return_value = _fake_graph()

    email_data = {
        "message_id": "<real-1@testcompany.com>",
        "in_reply_to": None,
        "from_address": "calisan@testcompany.com",
        "subject": "Izin sorusu",
        "body": "Izin hakkim ne zaman basliyor?",
    }

    result = process_single_email(email_data, db_session)

    assert result["status"] == "processed"
    mock_send_reply.assert_called_once()
    assert mock_send_reply.call_args.kwargs["to_address"] == "calisan@testcompany.com"
