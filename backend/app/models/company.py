import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email_domain = Column(String, nullable=False, unique=True)
    # İK'ya yönlendirilen sorular bu adrese bildirilir (boşsa HR_NOTIFY_EMAIL ayarı, o da boşsa yalnızca yıldız)
    hr_notify_email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Company {self.name}>"
