from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocumentChunk, Document
from app.models.document import DocumentStatus, DocumentVisibility
from app.services.document_processor import get_embedding

RAG_TOP_K = settings.RAG_TOP_K
RAG_CONFIDENCE_THRESHOLD = settings.RAG_CONFIDENCE_THRESHOLD


def search_relevant_chunks(company_id: str, query_text: str, db: Session, include_internal: bool = True) -> list[dict]:
    """
    Verilen soru metnine, belirtilen şirkete ait, ONAYLANMIŞ dokümanlar arasından
    en yakın RAG_TOP_K chunk'ı bulur. Her sonuç için benzerlik skoru ve
    eşik üstünde olup olmadığı bilgisini döner.

    include_internal=False ise yalnızca herkese açık (public) belgeler aranır:
    dışarıdan yazan birine şirket içi politika asla cevap kaynağı olmaz.
    """
    query_vector = get_embedding(query_text)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)

    query = (
        db.query(DocumentChunk, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.status == DocumentStatus.APPROVED)   # Faz 3 sonundaki güvenlik notu
        .filter(DocumentChunk.company_id == company_id)  # multi-tenancy filtresi
    )
    if not include_internal:
        query = query.filter(Document.visibility == DocumentVisibility.PUBLIC)

    results = (
        query
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


def search_relevant_chunks_multi(company_id: str, queries: list[str], db: Session, include_internal: bool = True) -> list[dict]:
    """Birden çok sorguyla arar, sonuçları chunk bazında birleştirir (aynı chunk için en yüksek benzerlik)
    ve en iyi RAG_TOP_K parçayı döner. Takip sorularında ("peki ya cuma günleri?") tek başına zayıf
    eşleşen güncel soru, önceki soruyla birleştirilmiş ikinci bir sorguyla desteklenir."""
    best: dict[str, dict] = {}
    for query in queries:
        if not (query or "").strip():
            continue
        for match in search_relevant_chunks(company_id, query, db, include_internal=include_internal):
            current = best.get(match["chunk_id"])
            if current is None or match["similarity"] > current["similarity"]:
                best[match["chunk_id"]] = match
    merged = sorted(best.values(), key=lambda m: m["similarity"], reverse=True)
    return merged[:RAG_TOP_K]
