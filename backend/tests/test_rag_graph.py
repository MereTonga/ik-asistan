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
