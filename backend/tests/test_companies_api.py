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
