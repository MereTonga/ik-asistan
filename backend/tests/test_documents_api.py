def test_list_documents_empty(client, test_company):
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == []


def test_get_document_not_found_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/documents/{fake_id}")
    assert response.status_code == 404


def test_list_documents_filters_by_status(client, db_session, test_company):
    from app.models import Document

    doc1 = Document(
        company_id=test_company.id,
        original_filename="onaybekleyen.jpg",
        source_type="ocr_clean",
        status="pending_approval",
        raw_extracted_text="test metni",
    )
    doc2 = Document(
        company_id=test_company.id,
        original_filename="onayli.jpg",
        source_type="ocr_clean",
        status="approved",
        raw_extracted_text="test metni",
    )
    db_session.add_all([doc1, doc2])
    db_session.flush()

    response = client.get("/documents?status=pending_approval")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["original_filename"] == "onaybekleyen.jpg"

from unittest.mock import patch

def test_update_document_text_success(client, db_session, test_company):
    from app.models import Document

    doc = Document(
        company_id=test_company.id,
        original_filename="test.jpg",
        source_type="ocr_clean",
        status="pending_approval",
        raw_extracted_text="eski metin",
    )
    db_session.add(doc)
    db_session.flush()

    response = client.patch(
        f"/documents/{doc.id}",
        json={"raw_extracted_text": "düzeltilmiş metin"},
    )

    assert response.status_code == 200
    db_session.refresh(doc)
    assert doc.raw_extracted_text == "düzeltilmiş metin"


def test_update_document_text_rejects_approved_document(client, db_session, test_company):
    from app.models import Document

    doc = Document(
        company_id=test_company.id,
        original_filename="test.jpg",
        source_type="ocr_clean",
        status="approved",
        raw_extracted_text="onaylanmış metin",
    )
    db_session.add(doc)
    db_session.flush()

    response = client.patch(
        f"/documents/{doc.id}",
        json={"raw_extracted_text": "değişiklik denemesi"},
    )

    assert response.status_code == 400


@patch("app.api.documents.approve_document_task")
def test_approve_endpoint_triggers_celery_task(mock_task, client, db_session, test_company):
    from app.models import Document

    doc = Document(
        company_id=test_company.id,
        original_filename="test.jpg",
        source_type="ocr_clean",
        status="pending_approval",
        raw_extracted_text="test metni",
    )
    db_session.add(doc)
    db_session.flush()

    response = client.post(f"/documents/{doc.id}/approve")

    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(str(doc.id))