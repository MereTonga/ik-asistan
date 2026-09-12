import os
from typing import TypedDict
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

from langgraph.graph import StateGraph, END
from app.rag.retrieval import search_relevant_chunks

from app.logging_config import get_logger

logger = get_logger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL")
CONTEXT_SIZE = int(os.getenv("CONTEXT_SIZE", 4096))
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")

client = ollama.Client(host=OLLAMA_HOST)

GROUNDEDNESS_CHECK_ENABLED = os.getenv("GROUNDEDNESS_CHECK_ENABLED", "true").lower() == "true"

GROUNDEDNESS_PROMPT = """Sen bir doğrulama uzmanısın. Aşağıda bir KAYNAK METİN ve bu metne dayanarak üretilmiş bir CEVAP var.
Görevin: CEVAP'ta, KAYNAK METİN'de YER ALMAYAN somut, yanlış ya da uydurulmuş bir BİLGİ olup olmadığını kontrol etmek.

KAYNAK METİN:
{context}

CEVAP:
{answer}

ÖNEMLİ KURALLAR:
- CEVAP'ın "bu konuda kaynakta bilgi yok" ya da benzer şekilde DÜRÜSTÇE bir bilgi eksikliğini belirtmesi İHLAL DEĞİLDİR - bu doğru bir davranıştır, EVET say.
- Genel nezaket ifadeleri (selamlama, "yardımcı olmak isterim" gibi) İHLAL DEĞİLDİR, dikkate alma.
- Sadece KAYNAK METİN'le ÇELİŞEN ya da kaynakta hiç geçmeyen bir SAYI/KURAL/İDDİA varsa bunu ihlal say.

Eğer CEVAP bu kurallara göre kaynakla tutarlıysa "EVET" yaz.
Eğer CEVAP, kaynakla çelişen ya da kaynakta hiç olmayan somut bir bilgi/sayı/kural içeriyorsa "HAYIR" yaz.
SADECE "EVET" ya da "HAYIR" yaz, başka hiçbir şey yazma."""

# 1) STATE TANIMI — akış boyunca taşınacak veri paketi
class RAGState(TypedDict):
    company_id: str
    question: str
    retrieved_chunks: list       # arama sonucu bulunanlar
    has_confident_match: bool    # eşik üstünde en az bir chunk var mı
    answer: str                  # üretilen cevap veya yönlendirme mesajı
    was_escalated: bool          # insana yönlendirildi mi
    is_grounded: bool            # üretilen cevap dokümanla destekleniyor mu (grounded)


# 2) NODE'LAR — her biri State alır, güncellenmiş State döner

def search_node(state: RAGState) -> RAGState:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        chunks = search_relevant_chunks(state["company_id"], state["question"], db)
    finally:
        db.close()
    has_confident = any(c["is_confident"] for c in chunks)
    logger.info(f"search_node: has_confident_match={has_confident}, chunk_count={len(chunks)}")
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
        think=False,
    )
    logger.info(f"generate_answer_node: cevap üretildi -> '{response['message']['content']}...'")
    return {**state, "answer": response["message"]["content"], "was_escalated": False}


def escalate_node(state: RAGState) -> RAGState:
    message = "Bu konuda elimde net bir bilgi yok, talebinizi İK ekibimize ilettim."
    logger.info("escalate_node: yönlendirme yapılıyor")
    return {**state, "answer": message, "was_escalated": True}

def groundedness_check_node(state: RAGState) -> RAGState:
    if not GROUNDEDNESS_CHECK_ENABLED:
        return {**state, "is_grounded": True}

    confident_chunks = [c for c in state["retrieved_chunks"] if c["is_confident"]]
    context_text = "\n\n".join(c["chunk_text"] for c in confident_chunks)

    prompt = GROUNDEDNESS_PROMPT.format(context=context_text, answer=state["answer"])

    response = client.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"num_ctx": CONTEXT_SIZE, "temperature": 0},
        think=False,
    )

    verdict = response["message"]["content"].strip().upper()
    is_grounded = verdict.startswith("EVET")
    logger.info(f"groundedness_check_node: verdict={verdict}, is_grounded={is_grounded}")
    return {**state, "is_grounded": is_grounded}

# 3) KOŞULLU YÖNLENDİRME — search_node'dan sonra hangi node'a gidileceğine karar verir
def route_after_search(state: RAGState) -> str:
    return "generate_answer" if state["has_confident_match"] else "escalate"

def route_after_groundedness_check(state: RAGState) -> str:
    return "grounded" if state["is_grounded"] else "not_grounded"

# 4) GRAPH'I İNŞA ET
def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("search", search_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("groundedness_check", groundedness_check_node)
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

    graph.add_edge("generate_answer", "groundedness_check")

    graph.add_conditional_edges(
        "groundedness_check",
        route_after_groundedness_check,
        {
            "grounded": END,
            "not_grounded": "escalate",
        },
    )

    graph.add_edge("escalate", END)

    return graph.compile()
