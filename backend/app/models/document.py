import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base

EMBEDDING_BOYUTU = 1024  # qwen3-embedding:0.6b'nin ürettiği vektör boyutu

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=True)  # YENİ SATIR - diskteki gerçek dosya adı
    source_type = Column(String, nullable=False)  # 'pdf_text' | 'ocr_clean' | 'ocr_complex'
    status = Column(String, nullable=False, default="pending_approval")  # 'pending_approval' | 'approved'

    raw_extracted_text = Column(Text, nullable=True)  # onay ekranında gösterilecek ham çıktı
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Bir Document, birden fazla chunk'a sahip olabilir
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document {self.original_filename} ({self.status})>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_BOYUTU), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk {self.id} (doc={self.document_id})>"
