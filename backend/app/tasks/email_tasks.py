from email.utils import make_msgid

import redis
from redis.exceptions import LockError, LockNotOwnedError

from app.celery_app import celery_app
from app.config import settings
from app.db.session import SessionLocal
from app.email_service.processor import (
    find_company_by_email_domain,
    find_or_create_thread,
    is_already_processed,
)
from app.email_service.reader import ImapInbox, parse_email, parse_headers
from app.email_service.sender import send_hr_notification, send_reply
from app.logging_config import get_logger
from app.models import EmailThread, Message
from app.rag.graph import build_rag_graph

redis_client = redis.from_url(settings.REDIS_URL)

EMAIL_CHECK_LOCK_KEY = "ik:email_check_lock"
EMAIL_CHECK_LOCK_TTL = 300  # saniye; her mail işlendikten sonra yenilenir, toplam süreyi sınırlamaz
SKIP_KEY_PREFIX = "ik:email_skip:"   # atlanan mail → sebep (bilinmeyen domain, oto-yanıt); TTL EMAIL_SKIP_MEMORY_DAYS
RATE_KEY_PREFIX = "ik:email_rate:"   # gönderen → son 1 saatte işlenen mail sayısı

logger = get_logger(__name__)


def _skip_key(message_id: str) -> str:
    return f"{SKIP_KEY_PREFIX}{message_id}"


def _remember_skip(message_id: str, reason: str) -> None:
    redis_client.set(_skip_key(message_id), reason, ex=settings.EMAIL_SKIP_MEMORY_DAYS * 24 * 3600)


def _is_remembered_skip(message_id: str) -> bool:
    return bool(redis_client.exists(_skip_key(message_id)))


def _rate_limit_exceeded(sender: str) -> bool:
    """Aynı gönderenden saatte EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR'dan fazla mail işlenmez.
    Sayaç ilk mailde başlar ve 1 saat sonra kendiliğinden silinir."""
    key = f"{RATE_KEY_PREFIX}{(sender or '').lower()}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 3600)
    return count > settings.EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR


def _escalation_reason(rag_result: dict) -> str:
    if not rag_result.get("has_confident_match"):
        return "belgelerde soruya yeterince benzer içerik bulunamadı"
    if rag_result.get("is_grounded") is False:
        return "üretilen cevap kaynak belgeyle tutarlı bulunmadı"
    return "otomatik cevap üretilemedi"


def _notify_hr_if_configured(company, email_data: dict, rag_result: dict) -> None:
    """Şirketin (ya da genel ayarın) İK bildirim adresi varsa ve bu adres botun kendi kutusu değilse
    yönlendirilen soruyu oraya iletir. Bildirim hatası ana akışı bozmaz (cevap zaten gönderildi)."""
    address = (getattr(company, "hr_notify_email", None) or settings.HR_NOTIFY_EMAIL or "").strip().lower()
    if not address:
        return
    if address == (settings.EMAIL_ADDRESS or "").strip().lower():
        # Aynı kutu: mail zaten orada ve yıldızlı; ayrıca bildirim göndermek kopya üretir
        return
    try:
        send_hr_notification(
            hr_address=address,
            employee_address=email_data["from_address"],
            subject=email_data["subject"],
            question=email_data["body"],
            reason=_escalation_reason(rag_result),
        )
        logger.info(f"İK bildirimi gönderildi -> {address} (gönderen: {email_data['from_address']})")
    except Exception as e:
        logger.error(f"İK bildirimi gönderilemedi ({address}): {e}", exc_info=True)


def _discard_incoming_stamp(db, incoming_id, thread_id, thread_was_new) -> None:
    """Cevap üretilemedi/gönderilemedi: idempotency damgasını (gelen mesaj kaydını) geri al ki
    bir sonraki poll aynı maili yeniden denesin. Yeni açılmış boş thread de silinir."""
    db.query(Message).filter(Message.id == incoming_id).delete()
    if thread_was_new:
        remaining = db.query(Message).filter(Message.thread_id == thread_id).count()
        if remaining == 0:
            db.query(EmailThread).filter(EmailThread.id == thread_id).delete()
    db.commit()


def process_single_email(email_data: dict, db, company_override=None, send_email: bool = True) -> dict:
    """
    Tek bir e-postayı baştan sona işler: idempotency, thread eşleştirme,
    RAG, cevaplama, kayıt. Hem gerçek IMAP akışı hem de /test simülasyonu
    bu fonksiyonu kullanır - mantık tek bir yerde yaşar.

    Sıralama bilinçli: gelen mesaj ÖNCE commit edilir (idempotency damgası: aynı mail
    ikinci kez işlenemez), sonra cevap üretilip gönderilir, en son giden mesaj commit edilir.
    Cevap üretme/gönderme başarısız olursa damga geri alınır ve hata yukarı fırlatılır;
    böylece mail bir sonraki poll'da yeniden denenir, ama başarıyla gönderilmiş bir cevap
    asla ikinci kez gönderilmez.

    company_override: Verilirse, domain'e göre arama yapılmaz, doğrudan bu şirket kullanılır.
    send_email: False verilirse SMTP'ye hiç gidilmez (test paneli daima False geçer).
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
    db.commit()  # idempotency damgası
    incoming_id, thread_id = incoming_message.id, thread.id

    try:
        graph = build_rag_graph()
        rag_result = graph.invoke({
            "company_id": str(company.id),
            "question": email_data["body"],
            "retrieved_chunks": [],
            "has_confident_match": False,
            "answer": "",
            "was_escalated": False,
        })

        if send_email:
            sent_message_id = send_reply(
                to_address=email_data["from_address"],
                subject=email_data["subject"],
                body=rag_result["answer"],
                in_reply_to_message_id=email_data["message_id"],
                references=email_data.get("references") or [],
            )
        else:
            # Simülasyon: gönderim yok, kayıt için yine de benzersiz bir Message-ID üretilir
            sent_message_id = make_msgid()

        with db.begin_nested():
            outgoing_message = Message(
                thread_id=thread_id,
                message_id_header=sent_message_id,
                sender_type="ai_system",
                body=rag_result["answer"],
                was_escalated=rag_result["was_escalated"],
                # Eşik kalibrasyonu ve analitik için: en yüksek benzerlik ve groundedness sonucu
                confidence_score=rag_result.get("max_similarity"),
                is_grounded=rag_result.get("is_grounded"),
            )
            db.add(outgoing_message)
            if rag_result["was_escalated"]:
                thread.status = "escalated"
        db.commit()
    except Exception:
        _discard_incoming_stamp(db, incoming_id, thread_id, is_new)
        raise

    # Yönlendirme bildirimi: yalnızca gerçek akışta (simülasyonda değil), kayıt tamamlandıktan sonra
    if rag_result["was_escalated"] and send_email:
        _notify_hr_if_configured(company, email_data, rag_result)

    return {
        "status": "processed",
        "answer": rag_result["answer"],
        "was_escalated": rag_result["was_escalated"],
    }


@celery_app.task(name="check_new_emails", ignore_result=True)
def check_new_emails_task():
    """
    Celery Beat tarafından periyodik olarak tetiklenir. Gelen kutusundaki okunmamış mailleri
    önce yalnızca başlıklarıyla eler (hatırlanan atlamalar, zaten işlenmişler, oto-yanıtlar,
    bilinmeyen domain, hız sınırı), kalanları tam çekip process_single_email ile işler.
    Başarıyla işlenen mail \\Seen (cevaplandıysa) ya da \\Seen + \\Flagged (İK'ya yönlendirildiyse)
    olarak işaretlenir; atlananlar okunmamış kalır ki İK gelen kutusunda görsün.
    """
    lock = redis_client.lock(EMAIL_CHECK_LOCK_KEY, timeout=EMAIL_CHECK_LOCK_TTL, blocking=False)
    if not lock.acquire(blocking=False):
        logger.info("Önceki çalıştırma hâlâ devam ediyor")
        return {"skipped_run": True, "reason": "Önceki çalıştırma hâlâ devam ediyor"}

    db = SessionLocal()
    counters = {"processed": 0, "skipped": 0, "errors": 0}

    try:
        with ImapInbox() as inbox:
            uids = inbox.list_unseen_uids()
            headers = inbox.fetch_headers(uids)

            for uid in uids:
                try:
                    raw_header = headers.get(uid)
                    if raw_header is None:
                        continue
                    head = parse_headers(raw_header, uid)
                    message_id = head["message_id"] or inbox.synthetic_message_id(uid)

                    if _is_remembered_skip(message_id):
                        counters["skipped"] += 1
                        continue

                    if is_already_processed(message_id, db):
                        # Daha önce işlenmiş ama işaretlenememiş (örn. bağlantı kopmuş) → şimdi işaretle
                        inbox.mark_processed(uid)
                        counters["skipped"] += 1
                        continue

                    if head["auto_reply_reason"]:
                        logger.info(f"Oto-yanıt/sistem maili atlandı ({head['auto_reply_reason']}): {message_id}")
                        _remember_skip(message_id, head["auto_reply_reason"])
                        counters["skipped"] += 1
                        continue

                    company = find_company_by_email_domain(head["from_address"], db)
                    if company is None:
                        logger.info(f"Bilinmeyen domain, atlandı: {head['from_address']} ({message_id})")
                        _remember_skip(message_id, "unknown_domain")
                        counters["skipped"] += 1
                        continue

                    if _rate_limit_exceeded(head["from_address"]):
                        # Hatırlanmaz: sayaç bir saat sonra silinince mail yeniden değerlendirilir
                        logger.warning(f"Hız sınırı: {head['from_address']} bu saat içinde çok mail gönderdi; {message_id} ertelendi")
                        counters["skipped"] += 1
                        continue

                    email_data = parse_email(inbox.fetch_message(uid), uid)
                    email_data["message_id"] = message_id

                    result = process_single_email(email_data, db, company_override=company)
                    if result["status"] == "processed":
                        counters["processed"] += 1
                        inbox.mark_processed(uid, flagged=bool(result["was_escalated"]))
                    else:
                        counters["skipped"] += 1
                        if result.get("reason") == "already_processed":
                            inbox.mark_processed(uid)

                    try:
                        lock.extend(EMAIL_CHECK_LOCK_TTL, replace_ttl=True)
                    except LockError:
                        logger.warning("Kilit süresi dolmuştu, yenilenemedi")
                except Exception as e:
                    db.rollback()
                    counters["errors"] += 1
                    logger.error(f"Mail işlenirken hata oluştu (uid={uid}): {e}", exc_info=True)
                    continue

        return counters

    finally:
        db.close()
        try:
            lock.release()
        except (LockNotOwnedError, LockError):
            logger.warning("Kilit bizde değildi (süresi dolmuş olabilir); serbest bırakılamadı")
