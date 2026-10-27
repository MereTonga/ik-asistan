import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base

EMBEDDING_BOYUTU = 1024  # qwen3-embedding:0.6b'nin ürettiği vektör boyutu


class DocumentStatus:
    """Belgenin yaşam döngüsü (String kolon, Enum değil - bilinçli karar, bkz. Faz 2).

    upload → PROCESSING → (worker) → PENDING_APPROVAL | FAILED
    PENDING_APPROVAL → (onay) → INDEXING → (worker) → APPROVED | PENDING_APPROVAL (hata)
    APPROVED → (yeniden parçala) → INDEXING → APPROVED
    APPROVED → (emekliye ayır) → RETIRED → (yeniden etkinleştir) → INDEXING → APPROVED
    FAILED | PENDING_APPROVAL → (yeniden işle) → PROCESSING
    Her durumdan (PROCESSING/INDEXING hariç) → DELETE: chunk'lar, dosya ve kayıt kalıcı silinir
    """
    PROCESSING = "processing"            # OCR / PDF çıkarımı sürüyor
    PENDING_APPROVAL = "pending_approval"  # metin hazır, insan onayı bekliyor
    FAILED = "failed"                    # çıkarım başarısız, error_message dolu
    INDEXING = "indexing"                # chunk + embedding üretiliyor
    APPROVED = "approved"                # aramaya açık
    RETIRED = "retired"                  # aramadan çıkarıldı, kayıt ve metin duruyor (chunk'lar silindi)

    ALL = (PROCESSING, PENDING_APPROVAL, FAILED, INDEXING, APPROVED, RETIRED)
    BUSY = (PROCESSING, INDEXING)        # worker üzerinde çalışıyor; silinemez


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_company_id", "company_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=True)  # diskteki gerçek (UUID'li) dosya adı
    source_type = Column(String, nullable=False)  # 'pending' | 'pdf_text' | 'ocr_clean' | 'ocr_complex'
    document_quality = Column(String, nullable=True)  # görseller için 'clean' | 'complex' (yeniden işlemede gerekir)
    status = Column(String, nullable=False, default=DocumentStatus.PENDING_APPROVAL)  # bkz. DocumentStatus

    raw_extracted_text = Column(Text, nullable=True)  # onay ekranında gösterilecek ham çıktı
    error_message = Column(Text, nullable=True)  # son işleme/indeksleme hatası (varsa)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Bir Document, birden fazla chunk'a sahip olabilir
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document {self.original_filename} ({self.status})>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_company_id", "company_id"),
        # Kosinüs araması için yaklaşık en-yakın-komşu indeksi; küçük veride fark etmez,
        # chunk sayısı on binleri bulunca sıralı taramayı önler.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_BOYUTU), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk {self.id} (doc={self.document_id})>"
