import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture
def db_session():
    """
    Her test için temiz bir veritabanı oturumu sağlar.
    Test bitince (başarılı ya da başarısız fark etmez) yapılan
    tüm değişiklikler geri alınır - veritabanı hep temiz kalır.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_company(db_session):
    """Testlerde kullanılacak, otomatik oluşturulan bir şirket kaydı."""
    from app.models import Company

    company = Company(
        name="Test Şirketi",
        email_domain="testcompany.com",
    )
    db_session.add(company)
    db_session.flush()  # id'yi almak için, henüz commit etmeden
    return company
