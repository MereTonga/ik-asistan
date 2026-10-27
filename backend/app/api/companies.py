import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.email_service.processor import normalize_domain
from app.models import Company

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


def _clean_notify_email(value: str | None) -> str | None:
    """Boş/boşluk → None; doluysa biçim kontrolü ve küçük harf."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    if not _EMAIL_RE.match(cleaned):
        raise HTTPException(status_code=422, detail=f"Geçersiz e-posta adresi: '{value}'")
    return cleaned


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

    new_company = Company(name=name, email_domain=domain, hr_notify_email=_clean_notify_email(hr_notify_email))
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return _serialize(new_company)


class CompanyUpdate(BaseModel):
    """JSON gövde; yalnızca gönderilen alanlar değişir. `hr_notify_email` için "" ya da null adresi kaldırır."""
    name: str | None = None
    hr_notify_email: str | None = None


@router.patch("/{company_id}")
def update_company(company_id: uuid.UUID, payload: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı")

    if "name" in payload.model_fields_set:
        if not (payload.name or "").strip():
            raise HTTPException(status_code=422, detail="Şirket adı boş olamaz")
        company.name = payload.name.strip()
    if "hr_notify_email" in payload.model_fields_set:
        company.hr_notify_email = _clean_notify_email(payload.hr_notify_email)

    db.commit()
    db.refresh(company)
    return _serialize(company)
