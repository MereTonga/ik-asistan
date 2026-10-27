import json
import os
import uuid
from email.utils import make_msgid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company
from app.tasks.email_tasks import process_single_email

router = APIRouter(prefix="/test", tags=["test"])

TEST_EMAILS_PATH = os.path.join(
    os.path.dirname(__file__), "../email_service/test_data/test_emails.json"
)


@router.get("/scenarios")
def get_test_scenarios():
    with open(TEST_EMAILS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/simulate/{scenario_index}")
def simulate_email(scenario_index: int, company_id: uuid.UUID, external: bool = False, db: Session = Depends(get_db)):
    """external=true: senaryoyu dışarıdan yazan biri gibi çalıştırır (yalnızca herkese açık belgeler)."""
    with open(TEST_EMAILS_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    if scenario_index < 0 or scenario_index >= len(scenarios):
        raise HTTPException(status_code=404, detail="Geçersiz senaryo index'i")

    scenario = scenarios[scenario_index]

    # Test panelinde domain kontrolü atlanır - hangi şirket için test edildiği
    # doğrudan parametre olarak belirtilir (gerçek IMAP akışında bu, domain'den bulunur)
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı")

    email_data = {
        "message_id": make_msgid(),
        "in_reply_to": None,
        "from_address": scenario["sender"],
        "subject": scenario["subject"],
        "body": scenario["body"],
    }

    # Simülasyon hiçbir koşulda gerçek mail göndermez (EMAIL_DRY_RUN'dan bağımsız)
    result = process_single_email(email_data, db, company_override=company, send_email=False, is_internal=not external)
    result["external"] = external
    return result