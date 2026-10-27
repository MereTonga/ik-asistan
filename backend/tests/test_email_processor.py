from datetime import datetime, timedelta, timezone

from app.email_service.processor import (
    _normalize_subject,
    find_company_by_email_domain,
    find_or_create_thread,
    is_already_processed,
)
from app.models import EmailThread, Message


def _mail(**overrides):
    data = {
        "message_id": "<abc123@example.com>",
        "in_reply_to": None,
        "references": [],
        "from_address": "calisan@testcompany.com",
        "subject": "İzin Sorusu",
        "body": "Merhaba, izin hakkım nedir?",
    }
    data.update(overrides)
    return data


def _thread(db_session, company, **overrides):
    fields = dict(
        company_id=company.id,
        subject="İlk Soru",
        employee_email="calisan@testcompany.com",
        root_message_id_header="<root@example.com>",
        status="open",
    )
    fields.update(overrides)
    thread = EmailThread(**fields)
    db_session.add(thread)
    db_session.flush()
    return thread


# --- konu normalizasyonu --------------------------------------------------------

def test_normalize_subject_strips_repeated_and_turkish_prefixes():
    assert _normalize_subject("Re: Re: Mesai Sorusu") == "mesai sorusu"
    assert _normalize_subject("Ynt: RE: Fwd:  Mesai   Sorusu ") == "mesai sorusu"
    # Türkçe İ'nin lower() davranışı ne olursa olsun iki taraf aynı şekilde normalize edilmeli
    assert _normalize_subject("Ynt: İzin Sorusu") == _normalize_subject("İzin Sorusu")
    assert _normalize_subject("") == ""


# --- şirket bulma ------------------------------------------------------------------

def test_find_company_by_email_domain_is_case_insensitive(db_session, test_company):
    assert find_company_by_email_domain("Ali@TestCompany.COM", db_session).id == test_company.id
    assert find_company_by_email_domain("ali@baska.com", db_session) is None
    assert find_company_by_email_domain("bozuk-adres", db_session) is None


# --- thread eşleştirme -------------------------------------------------------------

def test_find_or_create_thread_creates_new_thread(db_session, test_company):
    thread, is_new = find_or_create_thread(_mail(), str(test_company.id), db_session)

    assert is_new is True
    assert thread.subject == "İzin Sorusu"
    assert thread.status == "open"
    assert thread.root_message_id_header == "<abc123@example.com>"


def test_find_or_create_thread_matches_by_in_reply_to_root(db_session, test_company):
    existing = _thread(db_session, test_company)

    reply = _mail(message_id="<reply@example.com>", in_reply_to="<root@example.com>", subject="Re: İlk Soru")
    thread, is_new = find_or_create_thread(reply, str(test_company.id), db_session)

    assert is_new is False
    assert thread.id == existing.id


def test_find_or_create_thread_matches_reply_to_bots_answer(db_session, test_company):
    """En yaygın senaryo: çalışan botun CEVABINA 'Yanıtla' der; In-Reply-To botun Message-ID'sidir,
    kök mesajın değil. Eski kod bunu hiç eşleştiremiyordu."""
    existing = _thread(db_session, test_company)
    db_session.add(Message(thread_id=existing.id, message_id_header="<bot-answer@ik-asistan>", sender_type="ai_system", body="Cevap"))
    db_session.flush()

    follow_up = _mail(message_id="<m3@example.com>", in_reply_to="<bot-answer@ik-asistan>", subject="Re: Bambaşka bir konu başlığı")
    thread, is_new = find_or_create_thread(follow_up, str(test_company.id), db_session)

    assert is_new is False
    assert thread.id == existing.id


def test_find_or_create_thread_matches_via_references_chain(db_session, test_company):
    existing = _thread(db_session, test_company)
    db_session.add(Message(thread_id=existing.id, message_id_header="<bot-answer@ik-asistan>", sender_type="ai_system", body="Cevap"))
    db_session.flush()

    follow_up = _mail(message_id="<m4@example.com>", in_reply_to="<bilinmeyen@baska>", references=["<root@example.com>", "<bot-answer@ik-asistan>"], subject="x")
    thread, is_new = find_or_create_thread(follow_up, str(test_company.id), db_session)

    assert is_new is False
    assert thread.id == existing.id


def test_find_or_create_thread_never_crosses_companies(db_session, test_company, test_company_b):
    """B şirketinin gönderdiği mail, In-Reply-To ile A şirketinin thread'ine bağlanamaz."""
    thread_a = _thread(db_session, test_company)
    db_session.add(Message(thread_id=thread_a.id, message_id_header="<bot-answer@ik-asistan>", sender_type="ai_system", body="Cevap"))
    db_session.flush()

    mail_from_b = _mail(message_id="<b1@bsirketitest.com>", in_reply_to="<bot-answer@ik-asistan>", from_address="x@bsirketitest.com", subject="Re: İlk Soru")
    thread, is_new = find_or_create_thread(mail_from_b, str(test_company_b.id), db_session)

    assert is_new is True
    assert thread.id != thread_a.id
    assert thread.company_id == test_company_b.id


def test_find_or_create_thread_heuristic_matches_escalated_thread_too(db_session, test_company):
    existing = _thread(db_session, test_company, status="escalated", subject="Mesai Ücreti")

    follow_up = _mail(message_id="<m5@example.com>", subject="Ynt: Mesai Ücreti")
    thread, is_new = find_or_create_thread(follow_up, str(test_company.id), db_session)

    assert is_new is False
    assert thread.id == existing.id


def test_find_or_create_thread_heuristic_ignores_resolved_and_old_threads(db_session, test_company):
    _thread(db_session, test_company, status="resolved", subject="Kapanmış Konu", root_message_id_header="<r1@x>")
    _thread(
        db_session, test_company, status="open", subject="Eski Konu", root_message_id_header="<r2@x>",
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
    )

    t1, new1 = find_or_create_thread(_mail(message_id="<a@x>", subject="Re: Kapanmış Konu"), str(test_company.id), db_session)
    t2, new2 = find_or_create_thread(_mail(message_id="<b@x>", subject="Re: Eski Konu"), str(test_company.id), db_session)

    assert new1 is True and t1.subject == "Re: Kapanmış Konu"
    assert new2 is True and t2.subject == "Re: Eski Konu"


def test_find_or_create_thread_heuristic_is_case_insensitive_on_sender(db_session, test_company):
    existing = _thread(db_session, test_company, employee_email="Calisan@TestCompany.com", subject="İzin")

    thread, is_new = find_or_create_thread(_mail(message_id="<c@x>", from_address="calisan@testcompany.com", subject="RE: İzin"), str(test_company.id), db_session)

    assert is_new is False and thread.id == existing.id


# --- idempotency ----------------------------------------------------------------------

def test_is_already_processed_detects_duplicate(db_session, test_company):
    thread = _thread(db_session, test_company, root_message_id_header=None)
    db_session.add(Message(thread_id=thread.id, message_id_header="<already-seen@example.com>", sender_type="employee", body="Bir soru"))
    db_session.flush()

    assert is_already_processed("<already-seen@example.com>", db_session) is True
    assert is_already_processed("<never-seen@example.com>", db_session) is False
    assert is_already_processed(None, db_session) is False


# --- Faz 18.2: gönderen çözümleme -------------------------------------------------

def test_resolve_sender_prefers_authorized_address_then_domain(db_session, test_company, test_company_b, monkeypatch):
    import app.email_service.processor as processor_module
    from app.email_service.processor import resolve_sender
    from app.models import AuthorizedSender

    monkeypatch.setattr(processor_module.settings, "DEFAULT_COMPANY_DOMAIN", None)
    db_session.add(AuthorizedSender(company_id=test_company_b.id, email="stajyer@gmail.com", note="stajyer"))
    db_session.flush()

    assert resolve_sender("Stajyer@Gmail.com", db_session) == (test_company_b, True)   # liste, büyük/küçük harf duyarsız
    assert resolve_sender("ali@testcompany.com", db_session) == (test_company, True)   # domain
    assert resolve_sender("biri@bilinmeyen.com", db_session) == (None, False)         # varsayılan şirket yok → atla
    assert resolve_sender("bozuk", db_session) == (None, False)


def test_resolve_sender_falls_back_to_default_company_as_external(db_session, test_company, monkeypatch):
    import app.email_service.processor as processor_module
    from app.email_service.processor import resolve_sender

    monkeypatch.setattr(processor_module.settings, "DEFAULT_COMPANY_DOMAIN", "TestCompany.com")

    assert resolve_sender("aday@outlook.com", db_session) == (test_company, False)
    assert resolve_sender("ali@testcompany.com", db_session) == (test_company, True)
