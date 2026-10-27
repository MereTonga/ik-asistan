import os
import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db.session import get_db
from app.email_service.processor import normalize_domain
from app.models import AuthorizedSender, Company, Document, DocumentChunk, EmailThread, Message
from app.tasks.email_tasks import clear_skip_memory

router = APIRouter(prefix="/companies", tags=["companies"])

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serialize(company: Company) -> dict:
    return {
        "id": str(company.id),
        "name": company.name,
        "email_domain": company.email_domain,
        "hr_notify_email": company.hr_notify_email,
        "created_at": company.created_at,
    }


def _serialize_sender(sender: AuthorizedSender) -> dict:
    return {
        "id": str(sender.id),
        "company_id": str(sender.company_id),
        "email": sender.email,
        "note": sender.note,
        "created_at": sender.created_at,
    }


def _clean_email(value: str | None, field: str = "e-posta adresi") -> str | None:
    """Boş/boşluk → None; doluysa biçim kontrolü ve küçük harf."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    if not _EMAIL_RE.match(cleaned):
        raise HTTPException(status_code=422, detail=f"Geçersiz {field}: '{value}'")
    return cleaned


def _get_company_or_404(company_id: uuid.UUID, db: Session) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı")
    return company


@router.get("")
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.created_at).all()
    return [_serialize(c) for c in companies]


@router.post("/add")
def add_company(
    db: Session = Depends(get_db),
    name: str = Form(...),
    email_domain: str = Form(...),
    hr_notify_email: str | None = Form(None),
):
    name = name.strip()
    domain = normalize_domain(email_domain)
    if not name:
        raise HTTPException(status_code=422, detail="Şirket adı boş olamaz")
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=422, detail=f"Geçersiz e-posta domain'i: '{email_domain}' (örnek: ornek-sirket.com)")

    # Gelen mail eşleştirmesi küçük harfle yapılır; aynı domain farklı yazımla iki kez kaydedilemez
    existing = db.query(Company).filter(func.lower(Company.email_domain) == domain).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Bu domain zaten '{existing.name}' şirketine kayıtlı")

    new_company = Company(name=name, email_domain=domain, hr_notify_email=_clean_email(hr_notify_email))
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    # Bu domain'den daha önce gelen mailler "bilinmeyen domain" olarak hatırlanmış olabilir; yeniden değerlendirilsin
    clear_skip_memory()
    return _serialize(new_company)


class CompanyUpdate(BaseModel):
    """JSON gövde; yalnızca gönderilen alanlar değişir. `hr_notify_email` için "" ya da null adresi kaldırır."""
    name: str | None = None
    hr_notify_email: str | None = None


@router.patch("/{company_id}")
def update_company(company_id: uuid.UUID, payload: CompanyUpdate, db: Session = Depends(get_db)):
    company = _get_company_or_404(company_id, db)

    if "name" in payload.model_fields_set:
        if not (payload.name or "").strip():
            raise HTTPException(status_code=422, detail="Şirket adı boş olamaz")
        company.name = payload.name.strip()
    if "hr_notify_email" in payload.model_fields_set:
        company.hr_notify_email = _clean_email(payload.hr_notify_email)

    db.commit()
    db.refresh(company)
    return _serialize(company)


@router.delete("/{company_id}")
def delete_company(company_id: uuid.UUID, force: bool = False, db: Session = Depends(get_db)):
    """Şirketi siler. Belgesi ya da yazışması varsa `force=true` olmadan 409 döner; `force=true` ile
    belgeler (chunk'lar ve dosyalar), yazışmalar (mesajlar) ve yetkili gönderenler de kalıcı olarak silinir."""
    company = _get_company_or_404(company_id, db)

    document_count = db.query(Document).filter(Document.company_id == company.id).count()
    thread_count = db.query(EmailThread).filter(EmailThread.company_id == company.id).count()
    if (document_count or thread_count) and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Şirketin {document_count} belgesi ve {thread_count} yazışması var. "
                "Hepsiyle birlikte silmek için ?force=true kullanın."
            ),
        )

    stored_filenames = [
        name for (name,) in db.query(Document.stored_filename).filter(Document.company_id == company.id) if name
    ]
    document_ids = db.query(Document.id).filter(Document.company_id == company.id)
    thread_ids = db.query(EmailThread.id).filter(EmailThread.company_id == company.id)

    db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(document_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.company_id == company.id).delete(synchronize_session=False)
    db.query(Message).filter(Message.thread_id.in_(thread_ids)).delete(synchronize_session=False)
    db.query(EmailThread).filter(EmailThread.company_id == company.id).delete(synchronize_session=False)
    db.query(AuthorizedSender).filter(AuthorizedSender.company_id == company.id).delete(synchronize_session=False)
    db.delete(company)
    db.commit()

    for name in stored_filenames:
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except FileNotFoundError:
            pass

    return {
        "id": str(company_id),
        "message": "Şirket silindi.",
        "deleted_documents": document_count,
        "deleted_threads": thread_count,
    }


# --- Yetkili gönderenler ------------------------------------------------------

class SenderCreate(BaseModel):
    email: str
    note: str | None = None


@router.get("/{company_id}/senders")
def list_senders(company_id: uuid.UUID, db: Session = Depends(get_db)):
    company = _get_company_or_404(company_id, db)
    senders = (
        db.query(AuthorizedSender)
        .filter(AuthorizedSender.company_id == company.id)
        .order_by(AuthorizedSender.created_at)
        .all()
    )
    return [_serialize_sender(s) for s in senders]


@router.post("/{company_id}/senders")
def add_sender(company_id: uuid.UUID, payload: SenderCreate, db: Session = Depends(get_db)):
    """Domain'i farklı olsa da bu şirketin çalışanı sayılacak bir adres ekler (kişisel e-posta kullanan
    çalışan/stajyer). Aynı adres yalnızca bir şirkete bağlanabilir."""
    company = _get_company_or_404(company_id, db)
    email = _clean_email(payload.email)
    if email is None:
        raise HTTPException(status_code=422, detail="E-posta adresi boş olamaz")

    existing = db.query(AuthorizedSender).filter(func.lower(AuthorizedSender.email) == email).first()
    if existing is not None:
        owner = db.query(Company).filter(Company.id == existing.company_id).first()
        raise HTTPException(status_code=409, detail=f"Bu adres zaten '{owner.name if owner else '?'}' şirketine kayıtlı")

    sender = AuthorizedSender(company_id=company.id, email=email, note=(payload.note or "").strip() or None)
    db.add(sender)
    db.commit()
    db.refresh(sender)

    # Bu adresten daha önce gelen mailler atlanmış olabilir; yeniden değerlendirilsin
    clear_skip_memory()
    return _serialize_sender(sender)


@router.delete("/{company_id}/senders/{sender_id}")
def delete_sender(company_id: uuid.UUID, sender_id: uuid.UUID, db: Session = Depends(get_db)):
    sender = (
        db.query(AuthorizedSender)
        .filter(AuthorizedSender.id == sender_id, AuthorizedSender.company_id == company_id)
        .first()
    )
    if sender is None:
        raise HTTPException(status_code=404, detail="Yetkili gönderen bulunamadı")
    db.delete(sender)
    db.commit()
    return {"id": str(sender_id), "message": "Yetkili gönderen silindi."}
