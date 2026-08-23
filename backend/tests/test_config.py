import pytest
from pydantic import ValidationError

from app.config import Settings


REQUIRED_FIELDS = dict(
    DATABASE_URL="postgresql://test",
    REDIS_URL="redis://test",
    OLLAMA_BASE_URL="http://test",
    LLM_MODEL="test-model",
    VL_MODEL="test-model",
    OCR_MODEL="test-model",
    EMBEDDING_MODEL="test-model",
    EMAIL_ADDRESS="test@example.com",
    EMAIL_APP_PASSWORD="secret",
    IMAP_SERVER="imap.test.com",
    SMTP_SERVER="smtp.test.com",
)


def test_settings_loads_with_all_required_fields():
    settings = Settings(_env_file=None, **REQUIRED_FIELDS)

    # Varsayılan değerlerin doğru geldiğini de doğrulayalım
    assert settings.CONTEXT_SIZE == 4096
    assert settings.EMAIL_DRY_RUN is True
    assert settings.RAG_CONFIDENCE_THRESHOLD == 0.55


def test_settings_raises_when_required_field_missing(monkeypatch: pytest.MonkeyPatch):
    # BaseSettings ortam değişkenlerini de okur; bu alanı özellikle temizleyip
    # testin gerçekten "eksik alan" senaryosunu doğrulamasını sağlıyoruz.
    monkeypatch.delenv("EMAIL_APP_PASSWORD", raising=False)

    incomplete = REQUIRED_FIELDS.copy()
    del incomplete["EMAIL_APP_PASSWORD"]

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **incomplete)

    assert "EMAIL_APP_PASSWORD" in str(exc_info.value)


def test_settings_parses_bool_from_string():
    settings = Settings(_env_file=None, **REQUIRED_FIELDS, EMAIL_DRY_RUN="false")
    assert settings.EMAIL_DRY_RUN is False
