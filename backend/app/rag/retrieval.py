import os
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

from app.models import DocumentChunk, Document
from app.services.document_processor import get_embedding

RAG_TOP_K = int(os.getenv("RAG_TOP_K", 3))
RAG_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_CONFIDENCE_THRESHOLD", 0.55))


def search_relevant_chunks(company_id: str, query_text: str, db: Session) -> list[dict]:
    """
    Verilen soru metnine, belirtilen şirkete ait, ONAYLANMIŞ dokümanlar arasından
    en yakın RAG_TOP_K chunk'ı bulur. Her sonuç için benzerlik skoru ve
    eşik üstünde olup olmadığı bilgisini döner.
    """
    query_vector = get_embedding(query_text)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)

    results = (
        db.query(DocumentChunk, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.status == "approved")   # Faz 3 sonundaki güvenlik notu
        .filter(DocumentChunk.company_id == company_id)  # multi-tenancy filtresi
        .order_by(distance)  # en küçük mesafe = en benzer, en üstte
        .limit(RAG_TOP_K)
        .all()
    )

    matches = []
    for chunk, dist in results:
        similarity = 1 - dist
        matches.append({
            "chunk_id": str(chunk.id),
            "chunk_text": chunk.chunk_text,
            "similarity": round(similarity, 4),
            "is_confident": similarity >= RAG_CONFIDENCE_THRESHOLD,
        })
    return matches
