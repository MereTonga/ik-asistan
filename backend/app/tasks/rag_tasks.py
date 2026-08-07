from app.celery_app import celery_app
from app.rag.graph import build_rag_graph


@celery_app.task(name="answer_question")
def answer_question_task(company_id: str, question: str):
    graph = build_rag_graph()
    initial_state = {
        "company_id": company_id,
        "question": question,
        "retrieved_chunks": [],
        "has_confident_match": False,
        "answer": "",
        "was_escalated": False,
    }
    result = graph.invoke(initial_state)
    return {
        "answer": result["answer"],
        "was_escalated": result["was_escalated"],
    }
