import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.db.session import SessionLocal
from app.rag.retrieval import search_relevant_chunks

# Faz 3'te kullandığımız test company_id'sini buraya yapıştır
COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188"

db = SessionLocal()
try:
    results = search_relevant_chunks(COMPANY_ID, "gömlek içinde ne kadar kaldı?", db)
    for r in results:
        print(f"[benzerlik={r['similarity']}] [eşik_üstü={r['is_confident']}]")
        print(r['chunk_text'][:100], "...\n")
finally:
    db.close()
