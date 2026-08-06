import os
from typing import TypedDict
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

from langgraph.graph import StateGraph, END
from app.rag.retrieval import search_relevant_chunks

LLM_MODEL = os.getenv("LLM_MODEL")
CONTEXT_SIZE = int(os.getenv("CONTEXT_SIZE", 4096))
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")

client = ollama.Client(host=OLLAMA_HOST)


# 1) STATE TANIMI — akış boyunca taşınacak veri paketi
class RAGState(TypedDict):
    company_id: str
    question: str
    db_session: object          # SQLAlchemy session (dışarıdan geçirilecek)
    retrieved_chunks: list       # arama sonucu bulunanlar
    has_confident_match: bool    # eşik üstünde en az bir chunk var mı
    answer: str                  # üretilen cevap veya yönlendirme mesajı
    was_escalated: bool          # insana yönlendirildi mi


# 2) NODE'LAR — her biri State alır, güncellenmiş State döner

def search_node(state: RAGState) -> RAGState:
    chunks = search_relevant_chunks(state["company_id"], state["question"], state["db_session"])
    has_confident = any(c["is_confident"] for c in chunks)
    return {**state, "retrieved_chunks": chunks, "has_confident_match": has_confident}


def generate_answer_node(state: RAGState) -> RAGState:
    # Sadece eşik üstündeki chunk'ları bağlam olarak kullan
    confident_chunks = [c for c in state["retrieved_chunks"] if c["is_confident"]]
    context_text = "\n\n".join(c["chunk_text"] for c in confident_chunks)

    system_prompt = f"""Sen bir şirketin İK asistanısın. Çalışanlara nazik, profesyonel ve kısa bir dille cevap veriyorsun.
Sadece aşağıdaki dokümanda yer alan bilgiyi kullanarak cevap ver. Dokümanda olmayan bir şey uydurma.

DOKÜMAN:
{context_text}
"""

    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["question"]},
        ],
        options={"num_ctx": CONTEXT_SIZE},
    )

    return {**state, "answer": response["message"]["content"], "was_escalated": False}


def escalate_node(state: RAGState) -> RAGState:
    message = "Bu konuda elimde net bir bilgi yok, talebinizi İK ekibimize ilettim."
    return {**state, "answer": message, "was_escalated": True}


# 3) KOŞULLU YÖNLENDİRME — search_node'dan sonra hangi node'a gidileceğine karar verir
def route_after_search(state: RAGState) -> str:
    return "generate_answer" if state["has_confident_match"] else "escalate"


# 4) GRAPH'I İNŞA ET
def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("search", search_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("search")

    graph.add_conditional_edges(
        "search",
        route_after_search,
        {
            "generate_answer": "generate_answer",
            "escalate": "escalate",
        },
    )

    graph.add_edge("generate_answer", END)
    graph.add_edge("escalate", END)

    return graph.compile()
