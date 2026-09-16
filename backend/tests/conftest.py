import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database():
    """Apply the current Alembic schema before any test accesses the database."""
    if not TEST_DATABASE_URL:
        pytest.fail("TEST_DATABASE_URL must be set to run database tests")

    alembic_config = Config(
        os.path.join(os.path.dirname(__file__), "../alembic.ini")
    )
    alembic_config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # env.py uses DATABASE_URL for normal application migrations.
    with patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL}):
        command.upgrade(alembic_config, "head")


@pytest.fixture
def db_connection():
    """
    Testin süresince açık kalan tek bir veritabanı bağlantısı + transaction.
    Bu bağlantıya bağlanan her session (db_session da, Celery task'ların
    içindeki monkeypatch'lenmiş SessionLocal'lar da) aynı transaction'ı
    paylaşır - hiçbiri gerçekten commit etmez, hepsi testin sonunda tek
    seferde rollback edilir.
    """
    connection = engine.connect()
    transaction = connection.begin()

    yield connection

    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(db_connection):
    """Her test için, paylaşılan bağlantıya bağlı bir veritabanı oturumu."""
    session = TestSessionLocal(bind=db_connection)
    yield session
    session.close()


@pytest.fixture
def test_session_factory(db_connection):
    """
    SessionLocal'a benzer davranan bir fabrika - her çağrıldığında YENİ bir
    session döner, ama hepsi aynı paylaşılan bağlantıya bağlıdır. Celery
    task'ların içindeki gerçek SessionLocal'ı bununla değiştirmek
    (monkeypatch) için kullanılır.
    """
    def factory():
        return TestSessionLocal(bind=db_connection)
    return factory


@pytest.fixture
def test_company(db_session):
    from app.models import Company

    company = Company(
        name="Test Şirketi",
        email_domain="testcompany.com",
    )
    db_session.add(company)
    db_session.flush()
    return company


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.documents import get_db as documents_get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[documents_get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    
@pytest.fixture
def test_company_b(db_session):
    """İzolasyon testleri için ikinci, bağımsız bir şirket."""
    from app.models import Company

    company = Company(
        name="B Şirketi Test",
        email_domain="bsirketitest.com",
    )
    db_session.add(company)
    db_session.flush()
    return company