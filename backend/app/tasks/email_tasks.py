import os
import redis
from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.logging_config import get_logger
from app.models import Message
from app.email_service.reader import fetch_unseen_emails
from app.email_service.sender import send_reply
from app.email_service.processor import (
    is_already_processed,
    find_company_by_email_domain,
    find_or_create_thread,
)
from app.rag.graph import build_rag_graph


redis_client = redis.from_url(os.getenv("REDIS_URL"))
EMAIL_CHECK_LOCK_KEY = "email_check_lock"
EMAIL_CHECK_LOCK_TTL = 300

logger = get_logger(__name__)

def process_single_email(email_data: dict, db, company_override=None) -> dict:
    """
    Tek bir e-postayı baştan sona işler: idempotency, thread eşleştirme,
    RAG, cevaplama, kayıt. Hem gerçek IMAP akışı hem de /test simülasyonu
    bu fonksiyonu kullanır - mantık tek bir yerde yaşar.
    
    company_override: Verilirse, domain'e göre arama yapılmaz, doğrudan bu
    şirket kullanılır (test panelinde, çeşitli domain'lerden gelen simüle
    edilmiş maillerin tek bir test şirketine bağlanabilmesi için).
    """
    if is_already_processed(email_data["message_id"], db):
        return {"status": "skipped", "reason": "already_processed"}

    company = company_override or find_company_by_email_domain(email_data["from_address"], db)
    if company is None:
        return {"status": "skipped", "reason": "unknown_domain"}

    thread, is_new = find_or_create_thread(email_data, str(company.id), db)

    incoming_message = Message(
        thread_id=thread.id,
        message_id_header=email_data["message_id"],
        sender_type="employee",
        body=email_data["body"],
    )
    db.add(incoming_message)

    graph = build_rag_graph()
    rag_result = graph.invoke({
        "company_id": str(company.id),
        "question": email_data["body"],
        "retrieved_chunks": [],
        "has_confident_match": False,
        "answer": "",
        "was_escalated": False,
    })

    sent_message_id = send_reply(
        to_address=email_data["from_address"],
        subject=email_data["subject"],
        body=rag_result["answer"],
        in_reply_to_message_id=email_data["message_id"],
    )

    outgoing_message = Message(
        thread_id=thread.id,
        message_id_header=sent_message_id,
        sender_type="ai_system",
        body=rag_result["answer"],
        was_escalated=rag_result["was_escalated"],
    )
    db.add(outgoing_message)

    if rag_result["was_escalated"]:
        thread.status = "escalated"

    db.commit()

    return {
        "status": "processed",
        "answer": rag_result["answer"],
        "was_escalated": rag_result["was_escalated"],
    }


@celery_app.task(name="check_new_emails")
def check_new_emails_task():
    """
    Celery Beat tarafından periyodik olarak tetiklenir.
    Gelen kutusunu kontrol eder, her yeni maili process_single_email ile işler.
    """
    lock_acquired = redis_client.set(EMAIL_CHECK_LOCK_KEY, "1", nx=True, ex=EMAIL_CHECK_LOCK_TTL)
    if not lock_acquired:
        logger.info("Önceki çalıştırma hâlâ devam ediyor")
        return {"skipped_run": True, "reason": "Önceki çalıştırma hâlâ devam ediyor"}

    db = SessionLocal()
    processed_count = 0
    skipped_count = 0

    try:
        emails = fetch_unseen_emails()

        for email_data in emails:
            try:
                result = process_single_email(email_data, db)
                if result["status"] == "processed":
                    processed_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Mail işlenirken hata oluştu (message_id={email_data.get('message_id')}): {e}",
                    exc_info=True,
                )
                skipped_count += 1
                continue

        return {"processed": processed_count, "skipped": skipped_count}

    finally:
        db.close()
        redis_client.delete(EMAIL_CHECK_LOCK_KEY)