import os
import shutil
import uuid as uuid_lib
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import SessionLocal
from app.models import Document, Company
from app.services.document_processor import process_document

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

    # 2) Karar ağacını çalıştır (Faz 3.2'de yazdığımız servis)
    try:
        result = process_document(saved_path, document_quality)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3) Document kaydını oluştur (henüz onaylanmamış)
    new_document = Document(
        company_id=company_id,
        original_filename=file.filename,
        source_type=result["source_type"],
        status="pending_approval",
        raw_extracted_text=result["extracted_text"],
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return {
        "id": str(new_document.id),
        "status": new_document.status,
        "source_type": new_document.source_type,
        "extracted_text": new_document.raw_extracted_text,
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

    # 1) Metni chunk'lara ayır
    chunks = chunk_text(document.raw_extracted_text)

    if len(chunks) == 0:
        raise HTTPException(status_code=400, detail="Metinden anlamlı chunk çıkarılamadı")

    # 2) Her chunk için embedding hesapla ve kaydet
    for chunk in chunks:
        embedding_vector = get_embedding(chunk)
        new_chunk = DocumentChunk(
            document_id=document.id,
            company_id=document.company_id,
            chunk_text=chunk,
            embedding=embedding_vector,
        )
        db.add(new_chunk)

    # 3) Dokümanı onaylanmış olarak işaretle
    document.status = "approved"
    db.commit()

    return {
        "id": str(document.id),
        "status": document.status,
        "chunk_count": len(chunks),
    }