import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Yüklenen belgelerin diskteki yeri (tek tanım; api ve worker aynı yolu kullanır)
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")


class Settings(BaseSettings):
    """
    Tüm yapılandırma tek yerden okunur. .env eksikse ya da bir alan geçersizse
    uygulama başlangıçta (fail-fast) ValidationError ile durur.
    Modüller bu nesneyi `from app.config import settings` ile kullanır;
    doğrudan os.getenv / load_dotenv kullanılmaz.
    """

    # Veritabanı
    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None  # sadece testlerde gerekli, üretimde zorunlu değil

    # Redis / Celery
    REDIS_URL: str

    # Ollama
    OLLAMA_BASE_URL: str
    LLM_MODEL: str
    VL_MODEL: str
    OCR_MODEL: str
    EMBEDDING_MODEL: str
    CONTEXT_SIZE: int = 4096

    # RAG
    RAG_CONFIDENCE_THRESHOLD: float = 0.55
    RAG_TOP_K: int = 3
    GROUNDEDNESS_CHECK_ENABLED: bool = True

    # E-posta
    EMAIL_ADDRESS: str
    EMAIL_APP_PASSWORD: str
    IMAP_SERVER: str
    IMAP_PORT: int = 993
    SMTP_SERVER: str
    SMTP_PORT: int = 587
    EMAIL_DRY_RUN: bool = True
    EMAIL_POLL_INTERVAL_SECONDS: float = 120

    # Loglama
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=os.path.join(BACKEND_DIR, "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
