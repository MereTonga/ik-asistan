from unittest.mock import patch


def _create_approved_chunk(db_session, company, filename, chunk_text):
    from app.models import Document, DocumentChunk

    doc = Document(
        company_id=company.id,
        original_filename=filename,
        source_type="manual_test",
        status="approved",
        raw_extracted_text=chunk_text,
    )
    db_session.add(doc)
    db_session.flush()

    chunk = DocumentChunk(
        document_id=doc.id,
        company_id=company.id,
        chunk_text=chunk_text,
        embedding=[0.1] * 1024,  # gerçek anlam önemsiz - sadece geçerli boyutta bir vektör
    )
    db_session.add(chunk)
    db_session.flush()
    return chunk


@patch("app.rag.retrieval.get_embedding")
def test_search_relevant_chunks_only_returns_own_company_data(
    mock_get_embedding, db_session, test_company, test_company_b
):
    from app.rag.retrieval import search_relevant_chunks

    mock_get_embedding.return_value = [0.1] * 1024

    _create_approved_chunk(db_session, test_company, "a_belgesi.md", "A ŞİRKETİNE ÖZEL İZİN BİLGİSİ")
    _create_approved_chunk(db_session, test_company_b, "b_belgesi.md", "B ŞİRKETİNE ÖZEL İZİN BİLGİSİ")

    # A şirketi adına arama yapınca, SADECE A'nın verisini görmeliyiz
    results_a = search_relevant_chunks(str(test_company.id), "izin hakkım nedir?", db_session)
    texts_a = [r["chunk_text"] for r in results_a]

    assert "A ŞİRKETİNE ÖZEL İZİN BİLGİSİ" in texts_a
    assert "B ŞİRKETİNE ÖZEL İZİN BİLGİSİ" not in texts_a

    # B şirketi adına arama yapınca, SADECE B'nin verisini görmeliyiz
    results_b = search_relevant_chunks(str(test_company_b.id), "izin hakkım nedir?", db_session)
    texts_b = [r["chunk_text"] for r in results_b]

    assert "B ŞİRKETİNE ÖZEL İZİN BİLGİSİ" in texts_b
    assert "A ŞİRKETİNE ÖZEL İZİN BİLGİSİ" not in texts_b


@patch("app.rag.retrieval.get_embedding")
def test_search_relevant_chunks_ignores_unapproved_documents_across_companies(
    mock_get_embedding, db_session, test_company, test_company_b
):
    """Faz 3-4'te tasarlanan 'sadece onaylı dokümanlar aranır' kuralının,
    çok şirketli bir ortamda da doğru çalıştığını doğrular."""
    from app.rag.retrieval import search_relevant_chunks
    from app.models import Document, DocumentChunk

    mock_get_embedding.return_value = [0.1] * 1024

    # A şirketine ait ama HENÜZ ONAYLANMAMIŞ bir doküman
    pending_doc = Document(
        company_id=test_company.id,
        original_filename="onay_bekleyen.md",
        source_type="manual_test",
        status="pending_approval",
        raw_extracted_text="ONAYLANMAMIŞ İÇERİK",
    )
    db_session.add(pending_doc)
    db_session.flush()

    pending_chunk = DocumentChunk(
        document_id=pending_doc.id,
        company_id=test_company.id,
        chunk_text="ONAYLANMAMIŞ İÇERİK",
        embedding=[0.1] * 1024,
    )
    db_session.add(pending_chunk)
    db_session.flush()

    results = search_relevant_chunks(str(test_company.id), "herhangi bir soru", db_session)
    texts = [r["chunk_text"] for r in results]

    assert "ONAYLANMAMIŞ İÇERİK" not in texts
