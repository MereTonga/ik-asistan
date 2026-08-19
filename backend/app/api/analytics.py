from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.models import Message, EmailThread

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/summary")
def get_analytics_summary(company_id: str, db: Session = Depends(get_db)):
    total_questions = (
        db.query(Message)
        .join(EmailThread)
        .filter(EmailThread.company_id == company_id, Message.sender_type == "employee")
        .count()
    )

    escalated_count = (
        db.query(Message)
        .join(EmailThread)
        .filter(
            EmailThread.company_id == company_id,
            Message.sender_type == "ai_system",
            Message.was_escalated == True,  # noqa: E712
        )
        .count()
    )

    escalated_topics = (
        db.query(EmailThread.subject, func.count(Message.id).label("count"))
        .join(Message)
        .filter(
            EmailThread.company_id == company_id,
            Message.sender_type == "ai_system",
            Message.was_escalated == True,  # noqa: E712
        )
        .group_by(EmailThread.subject)
        .order_by(func.count(Message.id).desc())
        .limit(10)
        .all()
    )

    return {
        "total_questions": total_questions,
        "escalated_count": escalated_count,
        "escalation_rate": round(escalated_count / total_questions, 2) if total_questions > 0 else 0,
        "top_escalated_topics": [
            {"subject": subject, "count": count} for subject, count in escalated_topics
        ],
    }
