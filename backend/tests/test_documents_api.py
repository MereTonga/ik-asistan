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
