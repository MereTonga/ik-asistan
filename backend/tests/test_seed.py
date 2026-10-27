import pytest

from app.models import Company, Document, DocumentChunk
from app.models.document import DocumentStatus, DocumentVisibility


@pytest.fixture
def seed_env(monkeypatch, test_session_factory):
    import app.tasks.document_tasks as document_tasks_module

    monkeypatch.setattr(document_tasks_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(document_tasks_module, "get_embedding", lambda text: [0.0] * 1024)


def test_seed_creates_companies_and_indexes_documents(seed_env, db_session):
    from app.seed import SEED_COMPANIES, SEED_DOCUMENT_COUNT, seed_demo

    result = seed_demo(db_session)

    assert result["companies_created"] == len(SEED_COMPANIES)
    assert result["documents_indexed"] == SEED_DOCUMENT_COUNT
    assert result["failed"] == 0

    domains = sorted(c.email_domain for c in db_session.query(Company))
    assert domains == sorted(c["email_domain"] for c in SEED_COMPANIES)

    for doc in db_session.query(Document):
        assert doc.status == DocumentStatus.APPROVED
        assert doc.source_type == "seed_markdown"
        chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
        assert chunks >= 3  # başlıklı Markdown birden çok chunk'a bölünmeli

    visibilities = {d.original_filename: d.visibility for d in db_session.query(Document)}
    assert visibilities["ornek_a_genel_bilgiler.md"] == DocumentVisibility.PUBLIC
    assert visibilities["ornek_a_politikalar.md"] == DocumentVisibility.INTERNAL


def test_seed_is_idempotent(seed_env, db_session):
    from app.seed import SEED_COMPANIES, SEED_DOCUMENT_COUNT, seed_demo

    seed_demo(db_session)
    second = seed_demo(db_session)

    assert second["companies_created"] == 0
    assert second["documents_indexed"] == 0
    assert second["skipped"] == SEED_DOCUMENT_COUNT
    assert db_session.query(Company).count() == len(SEED_COMPANIES)
    assert db_session.query(Document).count() == SEED_DOCUMENT_COUNT


def test_seed_reports_indexing_failure(seed_env, monkeypatch, db_session):
    import app.tasks.document_tasks as document_tasks_module
    from app.seed import SEED_DOCUMENT_COUNT, seed_demo

    def boom(text):
        raise ConnectionError("Ollama kapalı")

    monkeypatch.setattr(document_tasks_module, "get_embedding", boom)

    result = seed_demo(db_session)

    assert result["failed"] == SEED_DOCUMENT_COUNT
    assert result["documents_indexed"] == 0
    # Belge kaydı kalır ama onay bekler; Ollama açılınca panelden onaylanabilir.
    # (Görev kendi session'ıyla yazdı; bu session'ın önbelleğini tazelemek gerekir.)
    db_session.expire_all()
    statuses = {d.status for d in db_session.query(Document)}
    assert statuses == {DocumentStatus.PENDING_APPROVAL}
    assert all("Ollama kapalı" in d.error_message for d in db_session.query(Document))
