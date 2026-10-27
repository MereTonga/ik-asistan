from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tüm modellerimiz bu Base sınıfından türeyecek
Base = declarative_base()


def get_db():
    """FastAPI dependency: istek başına bir session açar, istek bitince kapatır.
    Tüm router'lar bunu kullanır; testlerde dependency_overrides ile tek noktadan değiştirilir."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
