import os

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import UPLOAD_DIR
from app.db.session import SessionLocal
from app.logging_config import get_logger
from app.models import Document, DocumentChunk
from app.models.document import DocumentStatus
from app.services.document_processor import process_document, chunk_text, get_embedding

logger = get_logger(__name__)

ERROR_MESSAGE_MAX_LEN = 1000


def _short_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text[:ERROR_MESSAGE_MAX_LEN]


def _index_document(db: Session, document: Document) -> int:
    """Belgenin eski chunk'larını siler, metni yeniden parçalayıp embedding'leriyle ekler.
    Chunk sayısını döner. Çağıran taraf transaction'ı yönetir."""
    text = (document.raw_extracted_text or "").strip()
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Metin boş ya da parçalanamayacak kadar kısa")

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    for chunk in chunks:
        db.add(
            DocumentChunk(
                document_id=document.id,
                company_id=document.company_id,
                chunk_text=chunk,
                embedding=get_embedding(chunk),
            )
        )
    return len(chunks)


def _run_indexing(document_id: str, revert_status: str) -> dict:
    """approve ve rechunk görevlerinin ortak gövdesi.

    Belge satırı kilitlenir (SELECT ... FOR UPDATE): aynı belge için iki görev
    aynı anda çalışırsa ikincisi beklemek zorunda kalır ve kilidi aldığında
    durumun artık INDEXING olmadığını görüp hiçbir şey yapmadan döner.
    Hata olursa chunk değişiklikleri savepoint ile geri alınır ve belge
    `revert_status` durumuna, hata mesajıyla birlikte döner.
    """
    db = SessionLocal()
    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .with_for_update()
            .first()
        )
        if document is None:
            return {"error": "Doküman bulunamadı"}
        if document.status != DocumentStatus.INDEXING:
            logger.info(f"indexing atlandı: belge {document_id} durumu '{document.status}'")
            return {"document_id": document_id, "status": "skipped", "reason": f"durum: {document.status}"}

        try:
            with db.begin_nested():
                chunk_count = _index_document(db, document)
        except Exception as e:
            logger.error(f"Belge indekslenemedi (document_id={document_id}): {e}", exc_info=True)
            document.status = revert_status
            document.error_message = _short_error(e)
            db.commit()
            return {"document_id": document_id, "status": revert_status, "error": document.error_message}

        document.status = DocumentStatus.APPROVED
        document.error_message = None
        db.commit()
        return {"document_id": document_id, "status": DocumentStatus.APPROVED, "chunk_count": chunk_count}
    finally:
        db.close()


@celery_app.task(name="process_uploaded_document")
def process_uploaded_document_task(document_id: str):
    """
    Yüklenen dosyayı işler (PDF metin katmanı ya da OCR) ve belgeyi onaya hazır hale getirir.
    Dosya yolu ve kalite bilgisi belge kaydından okunur (yeniden işlemede de aynı görev kullanılır).
    Hata olursa belge FAILED durumuna geçer ve hata mesajı kaydedilir; sessizce takılı kalmaz.
    """
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            return {"error": "Doküman bulunamadı"}

        try:
            if not document.stored_filename:
                raise ValueError("Belgenin diskteki dosya adı kayıtlı değil")
            file_path = os.path.join(UPLOAD_DIR, document.stored_filename)
            result = process_document(file_path, document.document_quality)
        except Exception as e:
            logger.error(f"Belge işlenemedi (document_id={document_id}): {e}", exc_info=True)
            document.status = DocumentStatus.FAILED
            document.error_message = _short_error(e)
            db.commit()
            return {"document_id": document_id, "status": DocumentStatus.FAILED, "error": document.error_message}

        document.source_type = result["source_type"]
        document.raw_extracted_text = result["extracted_text"]
        document.status = DocumentStatus.PENDING_APPROVAL
        document.error_message = None
        db.commit()

        return {"document_id": document_id, "status": DocumentStatus.PENDING_APPROVAL}
    finally:
        db.close()


@celery_app.task(name="approve_document")
def approve_document_task(document_id: str):
    """Onaylanan belgeyi parçalar ve embedding'ler; başarısız olursa belge yeniden onay bekler."""
    return _run_indexing(document_id, revert_status=DocumentStatus.PENDING_APPROVAL)


@celery_app.task(name="rechunk_document")
def rechunk_document_task(document_id: str):
    """Onaylı bir belgeyi güncel chunk'lama yöntemiyle yeniden indeksler; başarısız olursa eski chunk'lar korunur."""
    return _run_indexing(document_id, revert_status=DocumentStatus.APPROVED)
