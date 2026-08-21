from app.email_service.processor import find_or_create_thread, is_already_processed
from app.models import EmailThread


def test_find_or_create_thread_creates_new_thread(db_session, test_company):
    email_data = {
        "message_id": "<abc123@example.com>",
        "in_reply_to": None,
        "from_address": "calisan@testcompany.com",
        "subject": "İzin Sorusu",
        "body": "Merhaba, izin hakkım nedir?",
    }

    thread, is_new = find_or_create_thread(email_data, str(test_company.id), db_session)

    assert is_new is True
    assert thread.subject == "İzin Sorusu"
    assert thread.status == "open"


def test_find_or_create_thread_matches_by_in_reply_to(db_session, test_company):
    # Önce bir thread oluştur (kök mesaj)
    existing = EmailThread(
        company_id=test_company.id,
        subject="İlk Soru",
        employee_email="calisan@testcompany.com",
        root_message_id_header="<root@example.com>",
        status="open",
    )
    db_session.add(existing)
    db_session.flush()

    # Şimdi bu thread'e "cevap" olan bir mail simüle et
    reply_data = {
        "message_id": "<reply@example.com>",
        "in_reply_to": "<root@example.com>",
        "from_address": "calisan@testcompany.com",
        "subject": "Re: İlk Soru",
        "body": "Takip sorum var.",
    }

    thread, is_new = find_or_create_thread(reply_data, str(test_company.id), db_session)

    assert is_new is False
    assert thread.id == existing.id


def test_is_already_processed_detects_duplicate(db_session, test_company):
    from app.models import Message

    thread = EmailThread(
        company_id=test_company.id,
        subject="Test",
        employee_email="calisan@testcompany.com",
        status="open",
    )
    db_session.add(thread)
    db_session.flush()

    message = Message(
        thread_id=thread.id,
        message_id_header="<already-seen@example.com>",
        sender_type="employee",
        body="Bir soru",
    )
    db_session.add(message)
    db_session.flush()

    assert is_already_processed("<already-seen@example.com>", db_session) is True
    assert is_already_processed("<never-seen@example.com>", db_session) is False
