import pytest

from app.models.document import DocumentStatus


def _make_document(db_session, company, **overrides):
    from app.models import Document

    fields = dict(
        company_id=company.id,
        original_filename="test.jpg",
        stored_filename="abc.jpg",
        source_type="ocr_clean",
        document_quality="clean",
        status=DocumentStatus.INDEXING,
        raw_extracted_text="Bu ilk paragraf yeterince uzun bir metin.\n\nBu da ikinci paragraf, o da yeterince uzun.",
    )
    fields.update(overrides)
    doc = Document(**fields)
    db_session.add(doc)
    db_session.flush()
    return doc


@pytest.fixture
def tasks_module(monkeypatch, test_session_factory):
    import app.tasks.document_tasks as document_tasks_module

    monkeypatch.setattr(document_tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(document_tasks_module, "get_embedding", lambda text: [0.0] * 1024)
    return document_tasks_module


def _chunk_count(db_session, doc_id):
    from app.models import DocumentChunk

    return db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()


def test_approve_document_task_creates_chunks(tasks_module, db_session, test_company):
    doc = _make_document(db_session, test_company)

    result = tasks_module.approve_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.APPROVED
    assert result["chunk_count"] == 2
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.APPROVED
    assert doc.error_message is None
    assert _chunk_count(db_session, doc.id) == 2


def test_approve_document_task_is_idempotent_on_second_run(tasks_module, db_session, test_company):
    """Aynı belge için görev iki kez kuyruğa girse bile chunk'lar çoğalmaz."""
    doc = _make_document(db_session, test_company)

    tasks_module.approve_document_task(str(doc.id))
    second = tasks_module.approve_document_task(str(doc.id))

    assert second["status"] == "skipped"
    assert _chunk_count(db_session, doc.id) == 2


def test_approve_document_task_skips_when_status_is_not_indexing(tasks_module, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.PENDING_APPROVAL)

    result = tasks_module.approve_document_task(str(doc.id))

    assert result["status"] == "skipped"
    assert _chunk_count(db_session, doc.id) == 0


def test_approve_document_task_reverts_to_pending_on_embedding_failure(tasks_module, monkeypatch, db_session, test_company):
    def boom(text):
        raise ConnectionError("Ollama kapalı")

    monkeypatch.setattr(tasks_module, "get_embedding", boom)
    doc = _make_document(db_session, test_company)

    result = tasks_module.approve_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.PENDING_APPROVAL
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.PENDING_APPROVAL
    assert "Ollama kapalı" in doc.error_message
    assert _chunk_count(db_session, doc.id) == 0


def test_approve_document_task_fails_cleanly_on_empty_text(tasks_module, db_session, test_company):
    doc = _make_document(db_session, test_company, raw_extracted_text="   ")

    result = tasks_module.approve_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.PENDING_APPROVAL
    db_session.refresh(doc)
    assert "boş" in doc.error_message


def test_rechunk_document_task_replaces_old_chunks(tasks_module, db_session, test_company):
    from app.models import DocumentChunk

    doc = _make_document(db_session, test_company, status=DocumentStatus.INDEXING)
    old_chunk = DocumentChunk(document_id=doc.id, company_id=test_company.id, chunk_text="ESKİ CHUNK", embedding=[0.0] * 1024)
    db_session.add(old_chunk)
    db_session.flush()

    result = tasks_module.rechunk_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.APPROVED
    texts = [c.chunk_text for c in db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id)]
    assert "ESKİ CHUNK" not in texts
    assert len(texts) == 2


def test_rechunk_document_task_keeps_old_chunks_on_failure(tasks_module, monkeypatch, db_session, test_company):
    from app.models import DocumentChunk

    doc = _make_document(db_session, test_company, status=DocumentStatus.INDEXING)
    db_session.add(DocumentChunk(document_id=doc.id, company_id=test_company.id, chunk_text="ESKİ CHUNK", embedding=[0.0] * 1024))
    db_session.flush()

    def boom(text):
        raise ConnectionError("Ollama kapalı")

    monkeypatch.setattr(tasks_module, "get_embedding", boom)

    result = tasks_module.rechunk_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.APPROVED  # eski haline döner
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.APPROVED
    texts = [c.chunk_text for c in db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id)]
    assert texts == ["ESKİ CHUNK"]


def test_process_uploaded_document_task_updates_document(tasks_module, monkeypatch, db_session, test_company):
    seen = {}

    def fake_process(file_path, quality):
        seen["file_path"] = file_path
        seen["quality"] = quality
        return {"source_type": "ocr_clean", "extracted_text": "Sahte OCR çıktısı burada."}

    monkeypatch.setattr(tasks_module, "process_document", fake_process)
    doc = _make_document(
        db_session, test_company,
        source_type="pending", status=DocumentStatus.PROCESSING, raw_extracted_text=None, stored_filename="xyz.jpg",
    )

    result = tasks_module.process_uploaded_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.PENDING_APPROVAL
    assert seen["file_path"].endswith("uploads/xyz.jpg")
    assert seen["quality"] == "clean"
    db_session.refresh(doc)
    assert doc.source_type == "ocr_clean"
    assert doc.raw_extracted_text == "Sahte OCR çıktısı burada."
    assert doc.status == DocumentStatus.PENDING_APPROVAL


def test_process_uploaded_document_task_marks_failed_on_error(tasks_module, monkeypatch, db_session, test_company):
    def boom(file_path, quality):
        raise ValueError("Bu PDF'te metin katmanı yok, henüz desteklenmiyor.")

    monkeypatch.setattr(tasks_module, "process_document", boom)
    doc = _make_document(db_session, test_company, source_type="pending", status=DocumentStatus.PROCESSING, raw_extracted_text=None)

    result = tasks_module.process_uploaded_document_task(str(doc.id))

    assert result["status"] == DocumentStatus.FAILED
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.FAILED
    assert "metin katmanı yok" in doc.error_message
