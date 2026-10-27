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
