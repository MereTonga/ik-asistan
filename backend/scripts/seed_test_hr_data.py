import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.db.session import SessionLocal
from app.models import DocumentChunk
from app.services.document_processor import get_embedding

# Az önce psql'den dönen document id'yi buraya yapıştır
DOCUMENT_ID = "6cbfc090-e63f-4e03-81b2-b705295b9bed" # kendi document_id'n
COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188"  # kendi company_id'n

SAHTE_IK_METNI = """Çalışanlar işe başladıktan 1 yıl sonra yıllık izin hakkı kazanır.
1-5 yıl arası kıdemi olan çalışanlar 14 gün, 5 yıl üzeri kıdemi olan çalışanlar 20 gün yıllık izin kullanabilir.
İzin talepleri en az 3 iş günü önceden İK sistemine girilmelidir."""

db = SessionLocal()
try:
    embedding_vector = get_embedding(SAHTE_IK_METNI)
    chunk = DocumentChunk(
        document_id=DOCUMENT_ID,
        company_id=COMPANY_ID,
        chunk_text=SAHTE_IK_METNI,
        embedding=embedding_vector,
    )
    db.add(chunk)
    db.commit()
    print("Test chunk'ı eklendi.")
finally:
    db.close()
