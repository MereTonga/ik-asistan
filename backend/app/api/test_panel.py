import json
import os
from email.utils import make_msgid
from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.tasks.email_tasks import process_single_email

router = APIRouter(prefix="/test", tags=["test"])

TEST_EMAILS_PATH = os.path.join(
    os.path.dirname(__file__), "../email_service/test_data/test_emails.json"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/scenarios")
def get_test_scenarios():
    with open(TEST_EMAILS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/simulate/{scenario_index}")
def simulate_email(scenario_index: int, company_id: str, db: Session = Depends(get_db)):
    with open(TEST_EMAILS_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    if scenario_index < 0 or scenario_index >= len(scenarios):
        return {"error": "Geçersiz senaryo index'i"}

    scenario = scenarios[scenario_index]

    # Test panelinde domain kontrolü atlanır - hangi şirket için test edildiği
    # doğrudan parametre olarak belirtilir (gerçek IMAP akışında bu, domain'den bulunur)
    from app.models import Company
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        return {"error": "Geçersiz company_id"}

    email_data = {
        "message_id": make_msgid(),
        "in_reply_to": None,
        "from_address": scenario["sender"],
        "subject": scenario["subject"],
        "body": scenario["body"],
    }

    result = process_single_email(email_data, db, company_override=company)
    return result