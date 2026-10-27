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
