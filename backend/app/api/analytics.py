import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Message, EmailThread

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def get_analytics_summary(company_id: uuid.UUID, db: Session = Depends(get_db)):
    ai_messages = (
        db.query(Message)
        .join(EmailThread)
        .filter(EmailThread.company_id == company_id, Message.sender_type == "ai_system")
    )

    total_questions = (
        db.query(Message)
        .join(EmailThread)
        .filter(EmailThread.company_id == company_id, Message.sender_type == "employee")
        .count()
    )

    escalated_count = ai_messages.filter(Message.was_escalated == True).count()  # noqa: E712

    # Eşik kalibrasyonu için: cevaplanan/yönlendirilen sorularda en yüksek benzerlik ve groundedness oranı
    avg_confidence = (
        db.query(func.avg(Message.confidence_score))
        .join(EmailThread)
        .filter(EmailThread.company_id == company_id, Message.sender_type == "ai_system", Message.confidence_score.isnot(None))
        .scalar()
    )
    grounded_total = ai_messages.filter(Message.is_grounded.isnot(None)).count()
    grounded_true = ai_messages.filter(Message.is_grounded == True).count()  # noqa: E712

    # Dışarıdan yazanların (çalışan olmayan) soruları: yalnızca herkese açık belgelerle cevaplanır
    external_questions = (
        db.query(Message)
        .join(EmailThread)
        .filter(EmailThread.company_id == company_id, EmailThread.is_external == True, Message.sender_type == "employee")  # noqa: E712
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
        "avg_confidence_score": round(float(avg_confidence), 3) if avg_confidence is not None else None,
        "grounded_rate": round(grounded_true / grounded_total, 2) if grounded_total > 0 else None,
        "external_questions": external_questions,
        "top_escalated_topics": [
            {"subject": subject, "count": count} for subject, count in escalated_topics
        ],
    }
