import io
import os
from unittest.mock import patch

import pytest

from app.models.document import DocumentStatus

PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_HEADER = b"%PDF-1.4\n" + b"\x00" * 32


def _make_document(db_session, company, **overrides):
    from app.models import Document

    fields = dict(
        company_id=company.id,
        original_filename="test.jpg",
        stored_filename="test-stored.jpg",
        source_type="ocr_clean",
        status=DocumentStatus.PENDING_APPROVAL,
        raw_extracted_text="test metni",
    )
    fields.update(overrides)
    doc = Document(**fields)
    db_session.add(doc)
    db_session.flush()
    return doc


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    import app.api.documents as documents_module

    monkeypatch.setattr(documents_module, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


# --- liste / detay ---------------------------------------------------------

def test_list_documents_empty(client, test_company):
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == []


def test_get_document_not_found_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/documents/{fake_id}")
    assert response.status_code == 404


def test_list_documents_filters_by_status(client, db_session, test_company):
    _make_document(db_session, test_company, original_filename="onaybekleyen.jpg")
    _make_document(db_session, test_company, original_filename="onayli.jpg", status=DocumentStatus.APPROVED)

    response = client.get("/documents?status=pending_approval")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["original_filename"] == "onaybekleyen.jpg"


def test_list_documents_filters_by_company(client, db_session, test_company, test_company_b):
    _make_document(db_session, test_company, original_filename="a.jpg")
    _make_document(db_session, test_company_b, original_filename="b.jpg")

    response = client.get(f"/documents?company_id={test_company_b.id}")
    assert response.status_code == 200
    assert [d["original_filename"] for d in response.json()] == ["b.jpg"]


def test_get_document_detail_includes_new_fields(client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.FAILED, error_message="OCR patladı", document_quality="clean")

    response = client.get(f"/documents/{doc.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "OCR patladı"
    assert body["document_quality"] == "clean"
    assert body["company_id"] == str(test_company.id)


# --- metin düzenleme ---------------------------------------------------------

def test_update_document_text_success(client, db_session, test_company):
    doc = _make_document(db_session, test_company, raw_extracted_text="eski metin")

    response = client.patch(f"/documents/{doc.id}", json={"raw_extracted_text": "düzeltilmiş metin"})

    assert response.status_code == 200
    db_session.refresh(doc)
    assert doc.raw_extracted_text == "düzeltilmiş metin"


def test_update_document_text_rejects_approved_document(client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED)

    response = client.patch(f"/documents/{doc.id}", json={"raw_extracted_text": "değişiklik denemesi"})

    assert response.status_code == 400


def test_update_document_text_rejects_processing_document(client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.PROCESSING, raw_extracted_text=None)

    response = client.patch(f"/documents/{doc.id}", json={"raw_extracted_text": "x"})

    assert response.status_code == 409


# --- onay ---------------------------------------------------------------------

@patch("app.api.documents.approve_document_task")
def test_approve_endpoint_sets_indexing_and_triggers_task(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company)

    response = client.post(f"/documents/{doc.id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == DocumentStatus.INDEXING
    mock_task.delay.assert_called_once_with(str(doc.id))
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.INDEXING


@patch("app.api.documents.approve_document_task")
def test_approve_endpoint_second_click_is_rejected(mock_task, client, db_session, test_company):
    """İlk tıklama durumu INDEXING yapar; ikinci tıklama kuyruğa ikinci görev atamaz."""
    doc = _make_document(db_session, test_company)

    first = client.post(f"/documents/{doc.id}/approve")
    second = client.post(f"/documents/{doc.id}/approve")

    assert first.status_code == 200
    assert second.status_code == 409
    assert mock_task.delay.call_count == 1


@patch("app.api.documents.approve_document_task")
def test_approve_endpoint_rejects_empty_text(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, raw_extracted_text="   ")

    response = client.post(f"/documents/{doc.id}/approve")

    assert response.status_code == 409
    mock_task.delay.assert_not_called()


@patch("app.api.documents.approve_document_task")
def test_approve_endpoint_rejects_failed_document(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.FAILED, raw_extracted_text=None)

    response = client.post(f"/documents/{doc.id}/approve")

    assert response.status_code == 409
    mock_task.delay.assert_not_called()


# --- yeniden işle / yeniden parçala ------------------------------------------

@patch("app.api.documents.process_uploaded_document_task")
def test_reprocess_failed_document(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.FAILED, error_message="hata", raw_extracted_text=None)

    response = client.post(f"/documents/{doc.id}/reprocess")

    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(str(doc.id))
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.PROCESSING
    assert doc.error_message is None


@patch("app.api.documents.process_uploaded_document_task")
def test_reprocess_rejects_approved_document(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED)

    response = client.post(f"/documents/{doc.id}/reprocess")

    assert response.status_code == 409
    mock_task.delay.assert_not_called()


@patch("app.api.documents.rechunk_document_task")
def test_rechunk_approved_document(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED)

    response = client.post(f"/documents/{doc.id}/rechunk")

    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(str(doc.id))
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.INDEXING


@patch("app.api.documents.rechunk_document_task")
def test_rechunk_rejects_pending_document(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company)

    response = client.post(f"/documents/{doc.id}/rechunk")

    assert response.status_code == 409
    mock_task.delay.assert_not_called()


# --- yükleme ------------------------------------------------------------------

@patch("app.api.documents.process_uploaded_document_task")
def test_upload_png_creates_processing_document_and_saves_file(mock_task, client, db_session, test_company, upload_dir):
    from app.models import Document

    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "clean"},
        files={"file": ("belge.png", io.BytesIO(PNG_HEADER), "image/png")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == DocumentStatus.PROCESSING
    mock_task.delay.assert_called_once_with(body["id"])

    doc = db_session.query(Document).filter(Document.id == body["id"]).one()
    assert doc.document_quality == "clean"
    assert doc.source_type == "pending"
    assert doc.stored_filename.endswith(".png")
    assert os.path.exists(os.path.join(upload_dir, doc.stored_filename))


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_pdf_does_not_need_quality(mock_task, client, db_session, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id)},
        files={"file": ("politika.pdf", io.BytesIO(PDF_HEADER), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    mock_task.delay.assert_called_once()


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_image_without_quality_is_rejected(mock_task, client, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id)},
        files={"file": ("belge.png", io.BytesIO(PNG_HEADER), "image/png")},
    )

    assert response.status_code == 400
    mock_task.delay.assert_not_called()
    assert list(upload_dir.iterdir()) == []


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_unknown_extension(mock_task, client, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "clean"},
        files={"file": ("zararli.html", io.BytesIO(b"<script>alert(1)</script>"), "text/html")},
    )

    assert response.status_code == 400
    mock_task.delay.assert_not_called()
    assert list(upload_dir.iterdir()) == []


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_content_not_matching_extension(mock_task, client, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "clean"},
        files={"file": ("sahte.png", io.BytesIO(b"<html>degil</html>"), "image/png")},
    )

    assert response.status_code == 400
    mock_task.delay.assert_not_called()
    assert list(upload_dir.iterdir()) == []


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_unknown_company(mock_task, client, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": "00000000-0000-0000-0000-000000000000", "document_quality": "clean"},
        files={"file": ("belge.png", io.BytesIO(PNG_HEADER), "image/png")},
    )

    assert response.status_code == 404
    mock_task.delay.assert_not_called()


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_invalid_company_id_and_quality(mock_task, client, test_company, upload_dir):
    bad_id = client.post(
        "/documents/upload",
        data={"company_id": "abc", "document_quality": "clean"},
        files={"file": ("belge.png", io.BytesIO(PNG_HEADER), "image/png")},
    )
    bad_quality = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "super"},
        files={"file": ("belge.png", io.BytesIO(PNG_HEADER), "image/png")},
    )

    assert bad_id.status_code == 422
    assert bad_quality.status_code == 422
    mock_task.delay.assert_not_called()


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_oversized_file_and_removes_partial(mock_task, monkeypatch, client, test_company, upload_dir):
    import app.api.documents as documents_module

    monkeypatch.setattr(documents_module, "MAX_UPLOAD_BYTES", 64)
    big = PNG_HEADER + b"\x00" * 200

    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "clean"},
        files={"file": ("buyuk.png", io.BytesIO(big), "image/png")},
    )

    assert response.status_code == 413
    mock_task.delay.assert_not_called()
    assert list(upload_dir.iterdir()) == []


# --- Faz 17.1: emekliye ayırma ve silme ---------------------------------------

def _add_chunks(db_session, doc, company, n=2):
    from app.models import DocumentChunk

    for i in range(n):
        db_session.add(DocumentChunk(document_id=doc.id, company_id=company.id, chunk_text=f"chunk {i} metni", embedding=[0.0] * 1024))
    db_session.flush()


def _chunk_count(db_session, doc_id):
    from app.models import DocumentChunk

    return db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()


def test_retire_removes_chunks_and_keeps_record(client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED)
    _add_chunks(db_session, doc, test_company)

    response = client.post(f"/documents/{doc.id}/retire")

    assert response.status_code == 200
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.RETIRED
    assert doc.raw_extracted_text == "test metni"
    assert _chunk_count(db_session, doc.id) == 0


def test_retire_rejects_non_approved(client, db_session, test_company):
    doc = _make_document(db_session, test_company)  # pending_approval

    assert client.post(f"/documents/{doc.id}/retire").status_code == 409


@patch("app.api.documents.rechunk_document_task")
def test_retired_document_can_be_reactivated_via_rechunk(mock_task, client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.RETIRED)

    response = client.post(f"/documents/{doc.id}/rechunk")

    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(str(doc.id))
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.INDEXING


def test_delete_removes_record_chunks_and_file(client, db_session, test_company, upload_dir):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED, stored_filename="silinecek.png")
    _add_chunks(db_session, doc, test_company)
    file_path = upload_dir / "silinecek.png"
    file_path.write_bytes(PNG_HEADER)
    doc_id = doc.id

    response = client.delete(f"/documents/{doc_id}")

    assert response.status_code == 200
    from app.models import Document

    assert db_session.query(Document).filter(Document.id == doc_id).count() == 0
    assert _chunk_count(db_session, doc_id) == 0
    assert not file_path.exists()


def test_delete_works_for_failed_document_without_file(client, db_session, test_company, upload_dir):
    doc = _make_document(db_session, test_company, status=DocumentStatus.FAILED, stored_filename=None, raw_extracted_text=None)

    assert client.delete(f"/documents/{doc.id}").status_code == 200
    assert client.get(f"/documents/{doc.id}").status_code == 404


def test_delete_rejects_busy_document(client, db_session, test_company, upload_dir):
    processing = _make_document(db_session, test_company, status=DocumentStatus.PROCESSING, raw_extracted_text=None)
    indexing = _make_document(db_session, test_company, status=DocumentStatus.INDEXING)

    assert client.delete(f"/documents/{processing.id}").status_code == 409
    assert client.delete(f"/documents/{indexing.id}").status_code == 409


# --- Faz 18.1: görünürlük ------------------------------------------------------

@patch("app.api.documents.process_uploaded_document_task")
def test_upload_defaults_to_internal_and_accepts_public(mock_task, client, db_session, test_company, upload_dir):
    from app.models import Document

    default = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id)},
        files={"file": ("a.pdf", io.BytesIO(PDF_HEADER), "application/pdf")},
    )
    public = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "visibility": "public"},
        files={"file": ("b.pdf", io.BytesIO(PDF_HEADER), "application/pdf")},
    )
    bad = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "visibility": "secret"},
        files={"file": ("c.pdf", io.BytesIO(PDF_HEADER), "application/pdf")},
    )

    assert default.status_code == 200 and public.status_code == 200
    assert bad.status_code == 422
    assert db_session.query(Document).filter(Document.id == default.json()["id"]).one().visibility == "internal"
    assert db_session.query(Document).filter(Document.id == public.json()["id"]).one().visibility == "public"


def test_visibility_can_be_changed_and_filtered(client, db_session, test_company):
    doc = _make_document(db_session, test_company, status=DocumentStatus.APPROVED)
    assert client.get(f"/documents/{doc.id}").json()["visibility"] == "internal"

    changed = client.patch(f"/documents/{doc.id}/visibility", json={"visibility": "public"})
    assert changed.status_code == 200
    db_session.refresh(doc)
    assert doc.visibility == "public"

    assert client.patch(f"/documents/{doc.id}/visibility", json={"visibility": "gizli"}).status_code == 422

    listed = client.get(f"/documents?company_id={test_company.id}&visibility=public").json()
    assert [d["id"] for d in listed] == [str(doc.id)]
    assert client.get(f"/documents?company_id={test_company.id}&visibility=internal").json() == []


# --- Faz 21.0: Markdown / düz metin yükleme ------------------------------------

@patch("app.api.documents.process_uploaded_document_task")
def test_upload_markdown_and_text_without_quality(mock_task, client, db_session, test_company, upload_dir):
    from app.models import Document

    md = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id), "document_quality": "clean"},  # metin için yok sayılır
        files={"file": ("politika.md", io.BytesIO("# Başlık\n\nİzin kuralları burada.".encode("utf-8")), "text/markdown")},
    )
    txt = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id)},
        files={"file": ("notlar.txt", io.BytesIO("Düz metin içeriği.".encode("utf-8")), "text/plain")},
    )

    assert md.status_code == 200, md.text
    assert txt.status_code == 200, txt.text
    doc = db_session.query(Document).filter(Document.id == md.json()["id"]).one()
    assert doc.document_quality is None and doc.stored_filename.endswith(".md")
    assert mock_task.delay.call_count == 2


@patch("app.api.documents.process_uploaded_document_task")
def test_upload_rejects_binary_disguised_as_text(mock_task, client, test_company, upload_dir):
    response = client.post(
        "/documents/upload",
        data={"company_id": str(test_company.id)},
        files={"file": ("sahte.md", io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00"), "text/markdown")},
    )

    assert response.status_code == 400
    mock_task.delay.assert_not_called()
    assert list(upload_dir.iterdir()) == []
