import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.db.session import SessionLocal
from app.rag.graph import build_rag_graph

COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188"  # kendi company_id'n

graph = build_rag_graph()

sorular = [
    "Yıllık izin hakkım ne zaman başlıyor?",       # dokümanda VAR -> cevapla beklenir
    "Şirket arabası kullanabilir miyim?",           # dokümanda YOK -> yönlendir beklenir
]

for soru in sorular:
    initial_state = {
        "company_id": COMPANY_ID,
        "question": soru,
        "retrieved_chunks": [],
        "has_confident_match": False,
        "answer": "",
        "was_escalated": False,
    }
    result = graph.invoke(initial_state)
    print(f"SORU: {soru}")
    print(f"YÖNLENDİRİLDİ Mİ: {result['was_escalated']}")
    print(f"CEVAP: {result['answer']}")
    print("-" * 60)
