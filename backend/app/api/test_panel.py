import json
import os
from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])

TEST_EMAILS_PATH = os.path.join(
    os.path.dirname(__file__), "../email_service/test_data/test_emails.json"
)


@router.get("/scenarios")
def get_test_scenarios():
    with open(TEST_EMAILS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
