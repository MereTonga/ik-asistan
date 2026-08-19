from app.models import Company
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Form
from app.db.session import SessionLocal

router = APIRouter(prefix="/companies", tags=["companies"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
@router.get("")
def list_companies(db: Session = Depends(get_db)):
    
    companies = db.query(Company).all()
    
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "email_domain": c.email_domain,
            "created_at": c.created_at,
        }
        for c in companies
    ]
    
    
@router.post("/add")
def add_company(db: Session = Depends(get_db), name: str = Form(...), email_domain: str = Form(...)):
    
    new_company = Company(
        name=name,
        email_domain=email_domain
    )
    
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return {
        "id": str(new_company.id),
        "name": new_company.name,
        "email_domain": new_company.email_domain,
        "created_at": new_company.created_at,
    }