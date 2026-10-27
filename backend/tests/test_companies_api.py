from unittest.mock import patch

def test_add_company_normalizes_domain(client, db_session, test_company):
    from app.models import Company

    response = client.post("/companies/add", data={"name": "  Yeni Şirket ", "email_domain": " @Yeni-Sirket.COM. "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Yeni Şirket"
    assert body["email_domain"] == "yeni-sirket.com"
    assert db_session.query(Company).filter(Company.email_domain == "yeni-sirket.com").count() == 1


def test_add_company_rejects_duplicate_domain_case_insensitively(client, test_company):
    response = client.post("/companies/add", data={"name": "Kopya", "email_domain": "TestCompany.com"})

    assert response.status_code == 409
    assert "Test Şirketi" in response.json()["detail"]


def test_add_company_rejects_invalid_domain_and_empty_name(client, test_company):
    bad_domain = client.post("/companies/add", data={"name": "X", "email_domain": "bu bir domain degil"})
    no_tld = client.post("/companies/add", data={"name": "X", "email_domain": "localhost"})
    empty_name = client.post("/companies/add", data={"name": "   ", "email_domain": "ornek.com"})

    assert bad_domain.status_code == 422
    assert no_tld.status_code == 422
    assert empty_name.status_code == 422


def test_list_companies_returns_created(client, test_company):
    response = client.get("/companies")

    assert response.status_code == 200
    assert [c["email_domain"] for c in response.json()] == ["testcompany.com"]


# --- Faz 17.2: hr_notify_email -------------------------------------------------

def test_add_company_with_hr_notify_email_and_patch(client, test_company):
    created = client.post("/companies/add", data={"name": "C", "email_domain": "c-sirketi.com", "hr_notify_email": " IK.Muduru@c-sirketi.com "})
    assert created.status_code == 200, created.text
    assert created.json()["hr_notify_email"] == "ik.muduru@c-sirketi.com"

    company_id = created.json()["id"]
    cleared = client.patch(f"/companies/{company_id}", json={"hr_notify_email": ""})
    assert cleared.status_code == 200
    assert cleared.json()["hr_notify_email"] is None

    renamed = client.patch(f"/companies/{company_id}", json={"name": "C Yeni", "hr_notify_email": "ik@c-sirketi.com"})
    assert renamed.json()["name"] == "C Yeni"
    assert renamed.json()["hr_notify_email"] == "ik@c-sirketi.com"

    # Gönderilmeyen alan değişmez
    untouched = client.patch(f"/companies/{company_id}", json={"name": "C Son"})
    assert untouched.json()["hr_notify_email"] == "ik@c-sirketi.com"


def test_company_rejects_invalid_hr_notify_email(client, test_company):
    assert client.post("/companies/add", data={"name": "D", "email_domain": "d.com", "hr_notify_email": "bozuk"}).status_code == 422
    assert client.patch(f"/companies/{test_company.id}", json={"hr_notify_email": "bozuk"}).status_code == 422
    assert client.patch(f"/companies/{test_company.id}", json={"name": "  "}).status_code == 422
    assert client.patch("/companies/00000000-0000-0000-0000-000000000000", json={"name": "x"}).status_code == 404


# --- Faz 18.2: yetkili gönderenler ve şirket silme -----------------------------

@patch("app.api.companies.clear_skip_memory", return_value=0)
def test_sender_crud_and_uniqueness(mock_clear, client, test_company, test_company_b):
    added = client.post(f"/companies/{test_company.id}/senders", json={"email": " Stajyer@Gmail.com ", "note": "yaz stajyeri"})
    assert added.status_code == 200, added.text
    assert added.json()["email"] == "stajyer@gmail.com"
    assert added.json()["note"] == "yaz stajyeri"
    mock_clear.assert_called_once()

    listed = client.get(f"/companies/{test_company.id}/senders").json()
    assert [s["email"] for s in listed] == ["stajyer@gmail.com"]

    duplicate = client.post(f"/companies/{test_company_b.id}/senders", json={"email": "stajyer@gmail.com"})
    assert duplicate.status_code == 409
    assert "Test Şirketi" in duplicate.json()["detail"]

    assert client.post(f"/companies/{test_company.id}/senders", json={"email": "bozuk"}).status_code == 422
    assert client.post("/companies/00000000-0000-0000-0000-000000000000/senders", json={"email": "a@b.com"}).status_code == 404

    sender_id = added.json()["id"]
    assert client.delete(f"/companies/{test_company_b.id}/senders/{sender_id}").status_code == 404  # başka şirketten silinemez
    assert client.delete(f"/companies/{test_company.id}/senders/{sender_id}").status_code == 200
    assert client.get(f"/companies/{test_company.id}/senders").json() == []


@patch("app.api.companies.clear_skip_memory", return_value=0)
def test_add_company_clears_skip_memory(mock_clear, client, test_company):
    client.post("/companies/add", data={"name": "E", "email_domain": "e-sirketi.com"})
    mock_clear.assert_called_once()


def test_delete_company_requires_force_when_it_has_data(client, db_session, test_company):
    from app.models import Document, EmailThread

    db_session.add(Document(company_id=test_company.id, original_filename="a.pdf", source_type="pdf_text", status="approved", raw_extracted_text="x"))
    db_session.add(EmailThread(company_id=test_company.id, subject="s", employee_email="c@testcompany.com", status="open"))
    db_session.flush()

    response = client.delete(f"/companies/{test_company.id}")

    assert response.status_code == 409
    assert "1 belgesi ve 1 yazışması" in response.json()["detail"]
    assert client.get("/companies").json() != []


def test_delete_company_force_removes_everything(client, db_session, test_company, monkeypatch, tmp_path):
    import app.api.companies as companies_module
    from app.models import AuthorizedSender, Company, Document, DocumentChunk, EmailThread, Message

    monkeypatch.setattr(companies_module, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "dosya.png").write_bytes(b"x")

    doc = Document(company_id=test_company.id, original_filename="a.png", stored_filename="dosya.png", source_type="ocr_clean", status="approved", raw_extracted_text="x")
    db_session.add(doc)
    db_session.flush()
    db_session.add(DocumentChunk(document_id=doc.id, company_id=test_company.id, chunk_text="c", embedding=[0.0] * 1024))
    thread = EmailThread(company_id=test_company.id, subject="s", employee_email="c@testcompany.com", status="open")
    db_session.add(thread)
    db_session.flush()
    db_session.add(Message(thread_id=thread.id, message_id_header="<m@x>", sender_type="employee", body="b"))
    db_session.add(AuthorizedSender(company_id=test_company.id, email="x@gmail.com"))
    db_session.flush()

    response = client.delete(f"/companies/{test_company.id}?force=true")

    assert response.status_code == 200, response.text
    assert response.json()["deleted_documents"] == 1 and response.json()["deleted_threads"] == 1
    assert db_session.query(Company).count() == 0
    assert db_session.query(Document).count() == 0
    assert db_session.query(DocumentChunk).count() == 0
    assert db_session.query(EmailThread).count() == 0
    assert db_session.query(Message).count() == 0
    assert db_session.query(AuthorizedSender).count() == 0
    assert not (tmp_path / "dosya.png").exists()


def test_delete_empty_company_without_force(client, db_session, test_company_b):
    assert client.delete(f"/companies/{test_company_b.id}").status_code == 200
    assert client.delete(f"/companies/{test_company_b.id}").status_code == 404
