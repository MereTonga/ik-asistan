from unittest.mock import patch


def test_approve_document_task_creates_chunks(monkeypatch, db_session, test_session_factory, test_company):
    import app.tasks.document_tasks as document_tasks_module
    from app.models import Document, DocumentChunk

    monkeypatch.setattr(document_tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(document_tasks_module, "get_embedding", lambda text: [0.0] * 1024)

    doc = Document(
        company_id=test_company.id,
        original_filename="test.jpg",
        source_type="ocr_clean",
        status="pending_approval",
        raw_extracted_text="Bu ilk paragraf yeterince uzun bir metin.\n\nBu da ikinci paragraf, o da yeterince uzun.",
    )
    db_session.add(doc)
    db_session.flush()

    result = document_tasks_module.approve_document_task(str(doc.id))

    assert result["status"] == "approved"
    assert result["chunk_count"] == 2

    db_session.refresh(doc)
    assert doc.status == "approved"

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .all()
    )
    assert len(chunks) == 2

def test_process_uploaded_document_task_updates_document(monkeypatch, db_session, test_session_factory, test_company):
    import app.tasks.document_tasks as document_tasks_module
    from app.models import Document

    monkeypatch.setattr(document_tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(
        document_tasks_module,
        "process_document",
        lambda file_path, quality: {
            "source_type": "ocr_clean",
            "extracted_text": "Sahte OCR çıktısı burada.",
        },
    )

    doc = Document(
        company_id=test_company.id,
        original_filename="test.jpg",
        source_type="pending",
        status="pending_approval",
        raw_extracted_text=None,
    )
    db_session.add(doc)
    db_session.flush()

    result = document_tasks_module.process_uploaded_document_task(
        str(doc.id), "/sahte/yol/test.jpg", "clean"
    )

    assert result["status"] == "processed"

    db_session.refresh(doc)
    assert doc.source_type == "ocr_clean"
    assert doc.raw_extracted_text == "Sahte OCR çıktısı burada."