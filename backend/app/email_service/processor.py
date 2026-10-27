import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EmailThread, Message, Company

# Takip maillerinin eski thread'e bağlanmaya devam ettiği durumlar (resolved thread'e yeni mail gelirse yeni thread açılır)
_MATCHABLE_THREAD_STATUSES = ("open", "escalated")

# Birden çok ön ek üst üste gelebilir: "Re: Ynt: Re: Konu"
_SUBJECT_PREFIX_RE = re.compile(r"^(\s*(re|fwd?|fw|ynt|aw|sv|vs|wg|tr)\s*:\s*)+", flags=re.IGNORECASE)


def _normalize_subject(subject: str) -> str:
    """'Re:', 'Fwd:', 'Ynt:' gibi önekleri (tekrarlı olsalar da) temizler, karşılaştırma için sadeleştirir."""
    cleaned = _SUBJECT_PREFIX_RE.sub("", (subject or "").strip())
    return " ".join(cleaned.split()).lower()


def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().lstrip("@").rstrip(".")


def is_already_processed(message_id: str | None, db: Session) -> bool:
    """Bu Message-ID'ye sahip bir mesaj daha önce işlendi mi kontrol eder (idempotency)."""
    if not message_id:
        return False
    existing = db.query(Message).filter(Message.message_id_header == message_id).first()
    return existing is not None


def find_company_by_email_domain(from_address: str, db: Session) -> Company | None:
    """Gönderenin e-posta domain'inden şirketi bulur (büyük/küçük harf duyarsız)."""
    if not from_address or "@" not in from_address:
        return None
    domain = normalize_domain(from_address.split("@")[-1])
    return db.query(Company).filter(func.lower(Company.email_domain) == domain).first()


def find_or_create_thread(email_data: dict, company_id: str, db: Session) -> tuple[EmailThread, bool]:
    """
    İki katmanlı thread eşleştirme (her iki katman da şirkete bağlıdır):
    1) In-Reply-To / References'taki kimliklerden herhangi biri bu şirketin bir mesajına
       (gelen ya da botun gönderdiği) aitse → o thread. Çalışan botun cevabına "Yanıtla"
       dediğinde In-Reply-To botun Message-ID'sidir; bu yüzden yalnızca kök mesaja bakmak yetmez.
    2) Bulunamazsa: aynı gönderen + aynı (öneklerden arındırılmış) konu + son N gün içinde
       açılmış open/escalated thread.
    Dönüş: (thread, is_new_thread)
    """
    candidate_ids = [mid for mid in [email_data.get("in_reply_to"), *email_data.get("references", [])] if mid]

    # Katman 1: Kesin eşleştirme (mesaj kimlikleri)
    if candidate_ids:
        matched_message = (
            db.query(Message)
            .join(EmailThread, Message.thread_id == EmailThread.id)
            .filter(Message.message_id_header.in_(candidate_ids), EmailThread.company_id == company_id)
            .order_by(Message.created_at.desc())
            .first()
        )
        if matched_message:
            return matched_message.thread, False

        root_thread = (
            db.query(EmailThread)
            .filter(EmailThread.root_message_id_header.in_(candidate_ids), EmailThread.company_id == company_id)
            .first()
        )
        if root_thread:
            return root_thread, False

    # Katman 2: Sezgisel eşleştirme
    normalized_subject = _normalize_subject(email_data.get("subject", ""))
    reopen_window = datetime.now(timezone.utc) - timedelta(days=settings.THREAD_MATCH_WINDOW_DAYS)
    sender = (email_data.get("from_address") or "").strip().lower()

    candidates = (
        db.query(EmailThread)
        .filter(
            EmailThread.company_id == company_id,
            func.lower(EmailThread.employee_email) == sender,
            EmailThread.status.in_(_MATCHABLE_THREAD_STATUSES),
            EmailThread.created_at >= reopen_window,
        )
        .order_by(EmailThread.created_at.desc())
        .all()
    )
    for candidate in candidates:
        if _normalize_subject(candidate.subject) == normalized_subject:
            return candidate, False

    # Hiçbiri eşleşmedi: yeni thread oluştur
    new_thread = EmailThread(
        company_id=uuid.UUID(str(company_id)),
        subject=email_data.get("subject") or "(konu yok)",
        employee_email=email_data["from_address"],
        root_message_id_header=email_data.get("message_id"),
        status="open",
    )
    db.add(new_thread)
    db.flush()  # id'yi almak için commit beklemeden flush ediyoruz
    return new_thread, True
