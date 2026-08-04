from fastapi import FastAPI
from app.api import documents
from app import models  # noqa: F401 - tüm modelleri SQLAlchemy'ye tanıtmak için

app = FastAPI(title="İK Asistanı API")
app.include_router(documents.router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "İK Asistanı API çalışıyor"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

