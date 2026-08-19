import os
from fastapi import FastAPI
from app.api import documents, test_panel, analytics
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app import models  # noqa: F401 - tüm modelleri SQLAlchemy'ye tanıtmak için

app = FastAPI(title="İK Asistanı API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(documents.router)
app.include_router(test_panel.router)
app.include_router(analytics.router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "İK Asistanı API çalışıyor"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

