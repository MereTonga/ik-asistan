import os
import shutil
import uuid as uuid_lib
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import SessionLocal
from app.models import Document, Company
from app.services.document_processor import process_document
from app.tasks.document_tasks import process_uploaded_document_task, approve_document_task

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../../uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    document_quality: str | None = Form(None),
    db: Session = Depends(get_db),
):
    # 1) Dosyayı diske kaydet
    file_extension = os.path.splitext(file.filename)[1]
    saved_filename = f"{uuid_lib.uuid4()}{file_extension}"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2) Önce boş bir Document kaydı oluştur (henüz işlenmedi)
    new_document = Document(
        company_id=company_id,
        original_filename=file.filename,
        source_type="pending",
        status="pending_approval",
        raw_extracted_text=None,
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    # 3) İşlemeyi Celery'ye devret (arka planda çalışacak)
    process_uploaded_document_task.delay(str(new_document.id), saved_path, document_quality)

    return {
        "id": str(new_document.id),
        "status": new_document.status,
        "message": "Belge işleme kuyruğa alındı, arka planda işleniyor.",
    }

from app.services.document_processor import chunk_text, get_embedding
from app.models import DocumentChunk


@router.post("/{document_id}/approve")
def approve_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Doküman bulunamadı")
    if document.status == "approved":
        raise HTTPException(status_code=400, detail="Bu doküman zaten onaylanmış")

    approve_document_task.delay(document_id)

    return {"id": document_id, "message": "Onay işlemi kuyruğa alındı, chunk'lar arka planda oluşturuluyor."}