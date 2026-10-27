import re

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.email_service.processor import normalize_domain
from app.models import Company

router = APIRouter(prefix="/companies", tags=["companies"])

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _serialize(company: Company) -> dict:
    return {
        "id": str(company.id),
        "name": company.name,
        "email_domain": company.email_domain,
        "created_at": company.created_at,
    }


@router.get("")
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.created_at).all()
    return [_serialize(c) for c in companies]


@router.post("/add")
def add_company(db: Session = Depends(get_db), name: str = Form(...), email_domain: str = Form(...)):
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

    new_company = Company(name=name, email_domain=domain)
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return _serialize(new_company)
