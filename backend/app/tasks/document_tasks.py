from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models import Document, DocumentChunk
from app.services.document_processor import process_document, chunk_text, get_embedding


@celery_app.task(name="process_uploaded_document")
def process_uploaded_document_task(document_id: str, file_path: str, document_quality: str | None):
    """
    Faz 3'teki upload akışının Celery versiyonu.
    Dosyayı işler, Document kaydını OCR/PDF sonucuyla günceller.
    """
    db = SessionLocal()
    try:
        result = process_document(file_path, document_quality)

        document = db.query(Document).filter(Document.id == document_id).first()
        document.source_type = result["source_type"]
        document.raw_extracted_text = result["extracted_text"]
        db.commit()

        return {"document_id": document_id, "status": "processed"}
    finally:
        db.close()


@celery_app.task(name="approve_document")
def approve_document_task(document_id: str):
    """
    Faz 3'teki approve akışının Celery versiyonu.
    Chunk'lama + embedding hesaplama.
    """
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            return {"error": "Doküman bulunamadı"}

        chunks = chunk_text(document.raw_extracted_text)
        for chunk in chunks:
            embedding_vector = get_embedding(chunk)
            new_chunk = DocumentChunk(
                document_id=document.id,
                company_id=document.company_id,
                chunk_text=chunk,
                embedding=embedding_vector,
            )
            db.add(new_chunk)

        document.status = "approved"
        db.commit()

        return {"document_id": document_id, "status": "approved", "chunk_count": len(chunks)}
    finally:
        db.close()
