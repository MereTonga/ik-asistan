from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Kısıtlar/indeksler her zaman isimli olsun: migration'larda isimsiz kısıt düşürülemiyor (Faz 15 bulgusu).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Tüm modellerimiz bu Base sınıfından türeyecek
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def get_db():
    """FastAPI dependency: istek başına bir session açar, istek bitince kapatır.
    Tüm router'lar bunu kullanır; testlerde dependency_overrides ile tek noktadan değiştirilir."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
