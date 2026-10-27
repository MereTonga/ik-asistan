"""Örnek veri yükleyici (demo / ilk kurulum / `docker compose down -v` sonrası).

Kullanım:
    docker compose exec api python -m app.seed          # Docker modunda
    cd backend && python -m app.seed                    # host'ta (.venv, Ollama erişilebilir olmalı)

backend/seed/ altındaki politika metinlerini SEED_COMPANIES'de tanımlı şirketlere belge olarak yükler,
chunk'lar ve embedding'lerini üretip onaylar (Ollama'nın çalışıyor olması gerekir). Var olan şirket ve
belgeleri atlar; tekrar çalıştırmak güvenlidir. Normal kullanımda gerek yoktur: belgeler panelden yüklenir.
"""
import os
import sys

from sqlalchemy import func

from app.config import BACKEND_DIR
from app.db.session import SessionLocal
from app.logging_config import get_logger
from app.models import Company, Document
from app.models.document import DocumentStatus, DocumentVisibility
from app.tasks.document_tasks import approve_document_task

logger = get_logger(__name__)

SEED_DIR = os.path.join(BACKEND_DIR, "seed")

# documents: (dosya adı, görünürlük). 'public' belgeler dışarıdan yazanlara da cevap kaynağı olur (Faz 18).
SEED_COMPANIES = [
    {
        "name": "Örnek A Şirketi",
        "email_domain": "ornek-a.com",
        "documents": [
            ("ornek_a_politikalar.md", DocumentVisibility.INTERNAL),
            ("ornek_a_genel_bilgiler.md", DocumentVisibility.PUBLIC),
        ],
    },
    {
        "name": "Örnek B Şirketi",
        "email_domain": "ornek-b.com",
        "documents": [("ornek_b_politikalar.md", DocumentVisibility.INTERNAL)],
    },
]

SEED_DOCUMENT_COUNT = sum(len(c["documents"]) for c in SEED_COMPANIES)


def seed_demo(db) -> dict:
    """Şirketleri ve belgeleri oluşturur; sonuç sayaçlarını döner."""
    result = {"companies_created": 0, "documents_indexed": 0, "skipped": 0, "failed": 0}

    for spec in SEED_COMPANIES:
        company = db.query(Company).filter(func.lower(Company.email_domain) == spec["email_domain"]).first()
        if company is None:
            company = Company(name=spec["name"], email_domain=spec["email_domain"])
            db.add(company)
            db.commit()
            db.refresh(company)
            result["companies_created"] += 1
            logger.info(f"seed: şirket oluşturuldu -> {company.name} ({company.email_domain})")

        for filename, visibility in spec["documents"]:
            exists = (
                db.query(Document)
                .filter(Document.company_id == company.id, Document.original_filename == filename)
                .first()
            )
            if exists is not None:
                result["skipped"] += 1
                continue

            with open(os.path.join(SEED_DIR, filename), encoding="utf-8") as f:
                text = f.read()

            document = Document(
                company_id=company.id,
                original_filename=filename,
                stored_filename=None,  # diskte dosya yok, metin doğrudan Markdown
                source_type="seed_markdown",
                visibility=visibility,
                status=DocumentStatus.INDEXING,
                raw_extracted_text=text,
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            # Senkron çalıştırılır (Celery kuyruğuna girmez); chunk + embedding için Ollama gerekir
            outcome = approve_document_task(str(document.id))
            if outcome.get("status") == DocumentStatus.APPROVED:
                result["documents_indexed"] += 1
                logger.info(f"seed: belge indekslendi -> {filename} ({outcome.get('chunk_count')} chunk)")
            else:
                result["failed"] += 1
                logger.error(f"seed: belge indekslenemedi -> {filename}: {outcome}")

    return result


def main() -> int:
    db = SessionLocal()
    try:
        result = seed_demo(db)
    finally:
        db.close()
    print(
        f"Seed tamamlandı: {result['companies_created']} şirket oluşturuldu, "
        f"{result['documents_indexed']} belge indekslendi, {result['skipped']} atlandı, {result['failed']} başarısız."
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
