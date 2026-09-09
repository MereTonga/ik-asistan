from unittest.mock import patch, MagicMock


def test_route_after_search_goes_to_generate_answer_when_confident():
    from app.rag.graph import route_after_search

    state = {"has_confident_match": True}
    assert route_after_search(state) == "generate_answer"


def test_route_after_search_goes_to_escalate_when_not_confident():
    from app.rag.graph import route_after_search

    state = {"has_confident_match": False}
    assert route_after_search(state) == "escalate"


def test_escalate_node_returns_fixed_message_without_calling_llm():
    from app.rag.graph import escalate_node

    state = {"retrieved_chunks": [], "has_confident_match": False}
    result = escalate_node(state)

    assert result["was_escalated"] is True
    assert "İK ekibimize ilettim" in result["answer"]


@patch("app.rag.graph.client")
def test_generate_answer_node_uses_only_confident_chunks(mock_client):
    from app.rag.graph import generate_answer_node

    # Sahte bir LLM cevabı tanımlıyoruz - gerçekte Ollama'ya hiç gidilmeyecek
    mock_client.chat.return_value = {
        "message": {"content": "Sahte ama gerçekçi bir cevap."}
    }

    state = {
        "question": "İzin hakkım ne zaman başlıyor?",
        "retrieved_chunks": [
            {"chunk_text": "Eşik üstü chunk", "is_confident": True},
            {"chunk_text": "Eşik altı chunk", "is_confident": False},
        ],
    }

    result = generate_answer_node(state)

    assert result["answer"] == "Sahte ama gerçekçi bir cevap."
    assert result["was_escalated"] is False

    # LLM'e gönderilen bağlamda SADECE eşik üstü chunk olduğunu doğrula
    call_args = mock_client.chat.call_args
    system_message = call_args.kwargs["messages"][0]["content"]
    assert "Eşik üstü chunk" in system_message
    assert "Eşik altı chunk" not in system_message

def test_groundedness_check_skips_llm_when_disabled(monkeypatch):
    import app.rag.graph as graph_module

    monkeypatch.setattr(graph_module, "GROUNDEDNESS_CHECK_ENABLED", False)

    state = {"retrieved_chunks": [], "answer": "herhangi bir cevap"}
    result = graph_module.groundedness_check_node(state)

    assert result["is_grounded"] is True


@patch("app.rag.graph.client")
def test_groundedness_check_parses_evet_as_grounded(mock_client, monkeypatch):
    import app.rag.graph as graph_module

    monkeypatch.setattr(graph_module, "GROUNDEDNESS_CHECK_ENABLED", True)
    mock_client.chat.return_value = {"message": {"content": "EVET"}}

    state = {
        "retrieved_chunks": [{"chunk_text": "İzin hakkı 1 yıl sonra başlar.", "is_confident": True}],
        "answer": "İzin hakkınız 1 yıl sonra başlar.",
    }
    result = graph_module.groundedness_check_node(state)

    assert result["is_grounded"] is True


@patch("app.rag.graph.client")
def test_groundedness_check_parses_hayir_as_not_grounded(mock_client, monkeypatch):
    import app.rag.graph as graph_module

    monkeypatch.setattr(graph_module, "GROUNDEDNESS_CHECK_ENABLED", True)
    mock_client.chat.return_value = {"message": {"content": "HAYIR"}}

    state = {
        "retrieved_chunks": [{"chunk_text": "İzin hakkı 1 yıl sonra başlar.", "is_confident": True}],
        "answer": "İzin hakkınız 6 ay sonra başlar ve 30 gündür.",
    }
    result = graph_module.groundedness_check_node(state)

    assert result["is_grounded"] is False


def test_route_after_groundedness_check_grounded():
    from app.rag.graph import route_after_groundedness_check

    assert route_after_groundedness_check({"is_grounded": True}) == "grounded"


def test_route_after_groundedness_check_not_grounded():
    from app.rag.graph import route_after_groundedness_check

    assert route_after_groundedness_check({"is_grounded": False}) == "not_grounded"