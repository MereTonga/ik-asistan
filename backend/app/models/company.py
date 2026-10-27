import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email_domain = Column(String, nullable=False, unique=True)
    # İK'ya yönlendirilen sorular bu adrese bildirilir (boşsa HR_NOTIFY_EMAIL ayarı, o da boşsa yalnızca yıldız)
    hr_notify_email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Domain'i farklı olsa da bu şirketin çalışanı sayılan adresler (kişisel e-posta kullanan çalışan/stajyer)
    authorized_senders = relationship("AuthorizedSender", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company {self.name}>"


class AuthorizedSender(Base):
    """Şirket domain'i dışından yazan ama şirket çalışanı sayılacak adresler.
    Eşleştirme sırası: önce bu tablo (tam adres), sonra domain (bkz. processor.resolve_sender)."""
    __tablename__ = "authorized_senders"
    __table_args__ = (Index("ix_authorized_senders_company_id", "company_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    email = Column(String, nullable=False, unique=True)  # her zaman küçük harf
    note = Column(String, nullable=True)  # "stajyer, kişisel adres" gibi serbest not
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="authorized_senders")

    def __repr__(self):
        return f"<AuthorizedSender {self.email} -> {self.company_id}>"
