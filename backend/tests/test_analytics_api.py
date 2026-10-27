from app.models import EmailThread, Message


def _conversation(db_session, company, subject, escalated, confidence, grounded, mid):
    thread = EmailThread(company_id=company.id, subject=subject, employee_email="c@testcompany.com", status="escalated" if escalated else "open")
    db_session.add(thread)
    db_session.flush()
    db_session.add(Message(thread_id=thread.id, message_id_header=f"<in-{mid}@x>", sender_type="employee", body="soru"))
    db_session.add(Message(
        thread_id=thread.id, message_id_header=f"<out-{mid}@x>", sender_type="ai_system", body="cevap",
        was_escalated=escalated, confidence_score=confidence, is_grounded=grounded,
    ))
    db_session.flush()


def test_analytics_summary_includes_confidence_and_grounded_rate(client, db_session, test_company, test_company_b):
    _conversation(db_session, test_company, "İzin", escalated=False, confidence=0.8, grounded=True, mid=1)
    _conversation(db_session, test_company, "Mesai", escalated=True, confidence=0.4, grounded=None, mid=2)
    _conversation(db_session, test_company, "Prim", escalated=True, confidence=0.6, grounded=False, mid=3)
    _conversation(db_session, test_company_b, "Başka şirket", escalated=True, confidence=0.1, grounded=False, mid=4)

    response = client.get(f"/analytics/summary?company_id={test_company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["total_questions"] == 3
    assert body["escalated_count"] == 2
    assert body["escalation_rate"] == 0.67
    assert body["avg_confidence_score"] == 0.6   # (0.8 + 0.4 + 0.6) / 3, B şirketi hariç
    assert body["grounded_rate"] == 0.5          # grounded bilinen 2 mesajdan 1'i
    assert [t["subject"] for t in body["top_escalated_topics"]] == ["Mesai", "Prim"] or sorted(t["subject"] for t in body["top_escalated_topics"]) == ["Mesai", "Prim"]


def test_analytics_summary_empty_company(client, test_company):
    response = client.get(f"/analytics/summary?company_id={test_company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["total_questions"] == 0
    assert body["avg_confidence_score"] is None
    assert body["grounded_rate"] is None


def test_analytics_summary_rejects_invalid_company_id(client):
    assert client.get("/analytics/summary?company_id=abc").status_code == 422
