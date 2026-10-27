from unittest.mock import patch


@patch("app.tasks.email_tasks.build_rag_graph")
def test_simulate_external_flag_uses_public_scope(mock_build_graph, client, db_session, test_company):
    from app.models import EmailThread

    seen = []

    class Graph:
        def invoke(self, state):
            seen.append(state)
            return {**state, "answer": "cevap", "was_escalated": False}

    mock_build_graph.return_value = Graph()

    # Farklı senaryolar: aynı gönderen + konu aynı thread'e bağlanır, dış gönderen işareti thread açılırken konur
    internal = client.post(f"/test/simulate/0?company_id={test_company.id}")
    external = client.post(f"/test/simulate/1?company_id={test_company.id}&external=true")

    assert internal.status_code == 200 and external.status_code == 200
    assert internal.json()["external"] is False and external.json()["external"] is True
    assert seen[0]["include_internal"] is True and seen[1]["include_internal"] is False
    assert db_session.query(EmailThread).filter(EmailThread.is_external == True).count() == 1  # noqa: E712
    assert client.post(f"/test/simulate/999?company_id={test_company.id}").status_code == 404


@patch("app.tasks.email_tasks.build_rag_graph")
def test_follow_up_question_joins_same_thread_with_history(mock_build_graph, client, db_session, test_company):
    from app.models import EmailThread

    seen = []

    class Graph:
        def invoke(self, state):
            seen.append(state)
            return {**state, "answer": f"cevap {len(seen)}", "was_escalated": False}

    mock_build_graph.return_value = Graph()

    first = client.post(f"/test/simulate/2?company_id={test_company.id}")
    follow = client.post(
        f"/test/simulate/2?company_id={test_company.id}",
        json={"question": "Peki sertifika programları da dahil mi?"},
    )

    assert first.status_code == 200 and follow.status_code == 200
    assert first.json()["is_follow_up"] is False
    assert follow.json()["is_follow_up"] is True
    assert follow.json()["question"] == "Peki sertifika programları da dahil mi?"
    assert db_session.query(EmailThread).count() == 1  # aynı thread
    assert seen[0]["history"] == []
    assert [m["role"] for m in seen[1]["history"]] == ["user", "assistant"]
    assert seen[1]["history"][1]["content"] == "cevap 1"
    assert seen[1]["question"] == "Peki sertifika programları da dahil mi?"


def test_scenarios_include_candidate_questions(client):
    subjects = [s["subject"] for s in client.get("/test/scenarios").json()]
    assert "Staj Başvurusu" in subjects and "Çalışma Belgesi Talebi" in subjects
