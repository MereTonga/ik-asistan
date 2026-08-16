import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import EmailThread, Message, Company


def _normalize_subject(subject: str) -> str:
    """'Re:', 'Fwd:' gibi önekleri temizler, karşılaştırma için sadeleştirir."""
    cleaned = re.sub(r"^(re|fwd|fw)\s*:\s*", "", subject.strip(), flags=re.IGNORECASE)
    return cleaned.strip().lower()


def is_already_processed(message_id: str, db: Session) -> bool:
    """Bu Message-ID'ye sahip bir mesaj daha önce işlendi mi kontrol eder (idempotency)."""
    if not message_id:
        return False
    existing = db.query(Message).filter(
        Message.message_id_header == message_id
    ).first()
    return existing is not None


def find_company_by_email_domain(from_address: str, db: Session) -> Company | None:
    """Gönderenin e-posta domain'inden şirketi bulur."""
    domain = from_address.split("@")[-1].lower()
    return db.query(Company).filter(Company.email_domain == domain).first()


def find_or_create_thread(email_data: dict, company_id: str, db: Session) -> tuple[EmailThread, bool]:
    """
    İki katmanlı thread eşleştirme:
    1) Message-ID/In-Reply-To ile kesin eşleştirme
    2) Bulunamazsa, aynı gönderen + benzer konu + son N gün içinde açılmış 'open' thread
    Dönüş: (thread, is_new_thread)
    """
    # Katman 1: Kesin eşleştirme
    if email_data["in_reply_to"]:
        thread = db.query(EmailThread).filter(
            EmailThread.root_message_id_header == email_data["in_reply_to"]
        ).first()
        if thread:
            return thread, False

    # Katman 2: Sezgisel eşleştirme
    normalized_subject = _normalize_subject(email_data["subject"])
    reopen_window = datetime.utcnow() - timedelta(days=30)  # Faz 2'de konuştuğumuz pencere

    candidates = db.query(EmailThread).filter(
        EmailThread.employee_email == email_data["from_address"],
        EmailThread.status == "open",
        EmailThread.created_at >= reopen_window,
    ).all()

    for candidate in candidates:
        if _normalize_subject(candidate.subject) == normalized_subject:
            return candidate, False

    # Hiçbiri eşleşmedi: yeni thread oluştur
    new_thread = EmailThread(
        company_id=company_id,
        subject=email_data["subject"],
        employee_email=email_data["from_address"],
        root_message_id_header=email_data["message_id"],
        status="open",
    )
    db.add(new_thread)
    db.flush()  # id'yi almak için commit beklemeden flush ediyoruz
    return new_thread, True
