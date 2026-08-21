import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class EmailThread(Base):
    __tablename__ = "email_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    subject = Column(String, nullable=False)
    employee_email = Column(String, nullable=False)

    # E-posta protokolünün kendi konuşma takip mekanizması (Faz 6'da kullanılacak)
    root_message_id_header = Column(String, nullable=True, unique=True)

    status = Column(String, nullable=False, default="open")  # 'open' | 'escalated' | 'resolved'
    created_at = Column(DateTime, default= lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EmailThread {self.subject} ({self.status})>"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("email_threads.id"), nullable=False)
    message_id_header = Column(String, nullable=True, unique=True)

    # Bu mesaj çalışandan mı geldi, sistem mi cevap verdi?
    sender_type = Column(String, nullable=False)  # 'employee' | 'ai_system' | 'hr_staff'

    body = Column(Text, nullable=False)

    # RAG kararını da kayıt altına alıyoruz (analitik + hata ayıklama için değerli)
    was_escalated = Column(Boolean, default=False)
    confidence_score = Column(String, nullable=True)  # basit tutuyoruz, ölçüm birimi netleşince değişebilir

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    thread = relationship("EmailThread", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.sender_type} @ {self.created_at}>"
