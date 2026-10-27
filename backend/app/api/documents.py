import os
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, settings
from app.db.session import get_db
from app.models import Company, Document, DocumentChunk
from app.models.document import DocumentStatus, DocumentVisibility
from app.tasks.document_tasks import (
    approve_document_task,
    process_uploaded_document_task,
    rechunk_document_task,
)

router = APIRouter(prefix="/documents", tags=["documents"])

# Yükleme doğrulaması: yalnızca bu uzantılar; ikili dosyalarda ilk baytlar (magic bytes), metin
# dosyalarında UTF-8 çözülebilirlik kontrol edilir.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
TEXT_EXTENSIONS = {".md", ".txt"}
ALLOWED_EXTENSIONS = {".pdf"} | IMAGE_EXTENSIONS | TEXT_EXTENSIONS
MAGIC_BYTES = {
    ".pdf": (b"%PDF",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
TEXT_PROBE_BYTES = 4096
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
COPY_CHUNK_SIZE = 1024 * 1024


class DocumentTextUpdate(BaseModel):
    raw_extracted_text: str


class DocumentVisibilityUpdate(BaseModel):
    visibility: Literal["internal", "public"]


def _serialize(document: Document, detail: bool = False) -> dict:
    data = {
        "id": str(document.id),
        "company_id": str(document.company_id),
        "original_filename": document.original_filename,
        "source_type": document.source_type,
        "status": document.status,
        "visibility": document.visibility,
        "error_message": document.error_message,
        "created_at": document.created_at.isoformat() if document.created_at else None,  # timestamptz → '+00:00' ile
    }
    if detail:
        data.update(
            {
                "stored_filename": document.stored_filename,
                "document_quality": document.document_quality,
                "raw_extracted_text": document.raw_extracted_text,
            }
        )
    return data


def _get_document_or_404(document_id: str, db: Session) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Doküman bulunamadı")
    return document


def _save_upload(file: UploadFile, extension: str) -> str:
    """Dosyayı doğrulayıp diske yazar, diskteki adı döner. Doğrulama geçmezse hiçbir şey yazılmaz;
    boyut sınırı aşılırsa yarım dosya silinir."""
    if extension in TEXT_EXTENSIONS:
        probe = file.file.read(TEXT_PROBE_BYTES)
        file.file.seek(0)
        if b"\x00" in probe:
            raise HTTPException(status_code=400, detail="Dosya metin dosyası değil (ikili içerik)")
        try:
            probe.decode("utf-8")
        except UnicodeDecodeError as e:
            # Çok baytlı bir karakterin ortasında kesilmiş olabilir; yalnızca başlangıçtaki hataları ele al
            if e.start < TEXT_PROBE_BYTES - 4:
                raise HTTPException(status_code=400, detail="Metin dosyası UTF-8 olarak okunamadı")
    else:
        head = file.file.read(8)
        file.file.seek(0)
        if not any(head.startswith(magic) for magic in MAGIC_BYTES[extension]):
            raise HTTPException(status_code=400, detail="Dosya içeriği uzantısıyla uyuşmuyor")

    saved_filename = f"{uuid.uuid4()}{extension}"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    written = 0
    with open(saved_path, "wb") as buffer:
        while True:
            chunk = file.file.read(COPY_CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                buffer.close()
                os.remove(saved_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"Dosya çok büyük (üst sınır {settings.MAX_UPLOAD_MB} MB)",
                )
            buffer.write(chunk)
    return saved_filename


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    company_id: uuid.UUID = Form(...),
    document_quality: Literal["clean", "complex"] | None = Form(None),
    visibility: Literal["internal", "public"] = Form(DocumentVisibility.INTERNAL),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı")

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya türü '{extension or '(yok)'}'. İzin verilenler: pdf, jpg, jpeg, png, md, txt",
        )
    if extension in IMAGE_EXTENSIONS and document_quality is None:
        raise HTTPException(status_code=400, detail="Görsel dosyalar için document_quality 'clean' ya da 'complex' olmalı")

    saved_filename = _save_upload(file, extension)

    new_document = Document(
        company_id=company.id,
        original_filename=file.filename,
        stored_filename=saved_filename,
        source_type="pending",
        document_quality=document_quality if extension in IMAGE_EXTENSIONS else None,
        visibility=visibility,
        status=DocumentStatus.PROCESSING,
        raw_extracted_text=None,
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    process_uploaded_document_task.delay(str(new_document.id))

    return {
        "id": str(new_document.id),
        "status": new_document.status,
        "message": "Belge işleme kuyruğa alındı, arka planda işleniyor.",
    }


@router.post("/{document_id}/approve")
def approve_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document_or_404(document_id, db)
    if document.status == DocumentStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Bu doküman zaten onaylanmış")
    if document.status != DocumentStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"Bu durumdaki doküman onaylanamaz: {document.status}")
    if not (document.raw_extracted_text or "").strip():
        raise HTTPException(status_code=409, detail="Onaylanacak metin boş; önce metni düzenleyin ya da belgeyi yeniden işleyin")

    # Durumu burada değiştirmek ikinci bir 'Onayla' tıklamasını daha kuyruğa girmeden engeller.
    document.status = DocumentStatus.INDEXING
    document.error_message = None
    db.commit()

    approve_document_task.delay(document_id)

    return {"id": document_id, "status": document.status, "message": "Onay işlemi kuyruğa alındı, chunk'lar arka planda oluşturuluyor."}


@router.post("/{document_id}/reprocess")
def reprocess_document(document_id: str, db: Session = Depends(get_db)):
    """Başarısız (ya da onay bekleyen) belgeyi diskteki dosyasından yeniden işler."""
    document = _get_document_or_404(document_id, db)
    if document.status not in (DocumentStatus.FAILED, DocumentStatus.PENDING_APPROVAL):
        raise HTTPException(status_code=409, detail=f"Bu durumdaki doküman yeniden işlenemez: {document.status}")
    if not document.stored_filename:
        raise HTTPException(status_code=409, detail="Belgenin diskteki dosyası kayıtlı değil; yeniden yükleyin")

    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    db.commit()

    process_uploaded_document_task.delay(document_id)

    return {"id": document_id, "status": document.status, "message": "Belge yeniden işleme kuyruğuna alındı."}


@router.post("/{document_id}/rechunk")
def rechunk_document(document_id: str, db: Session = Depends(get_db)):
    """Onaylı belgeyi güncel chunk'lama yöntemiyle yeniden indeksler; emekli belgeyi yeniden etkinleştirir."""
    document = _get_document_or_404(document_id, db)
    if document.status not in (DocumentStatus.APPROVED, DocumentStatus.RETIRED):
        raise HTTPException(status_code=409, detail=f"Yalnızca onaylı ya da emekli dokümanlar yeniden parçalanabilir (durum: {document.status})")

    document.status = DocumentStatus.INDEXING
    document.error_message = None
    db.commit()

    rechunk_document_task.delay(document_id)

    return {"id": document_id, "status": document.status, "message": "Yeniden parçalama kuyruğa alındı."}


@router.post("/{document_id}/retire")
def retire_document(document_id: str, db: Session = Depends(get_db)):
    """Onaylı belgeyi aramadan çıkarır: chunk'lar silinir, kayıt ve metin kalır (denetim izi).
    'Yeniden parçala' ile tekrar etkinleştirilebilir."""
    document = _get_document_or_404(document_id, db)
    if document.status != DocumentStatus.APPROVED:
        raise HTTPException(status_code=409, detail=f"Yalnızca onaylı dokümanlar emekliye ayrılabilir (durum: {document.status})")

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    document.status = DocumentStatus.RETIRED
    document.error_message = None
    db.commit()

    return {"id": document_id, "status": document.status, "message": "Belge aramadan çıkarıldı."}


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Belgeyi kalıcı olarak siler: chunk'lar, diskteki dosya ve kayıt. İşleme sürerken silinemez."""
    document = _get_document_or_404(document_id, db)
    if document.status in DocumentStatus.BUSY:
        raise HTTPException(status_code=409, detail=f"İşleme sürerken silinemez (durum: {document.status}); bitmesini bekleyin")

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    stored_filename = document.stored_filename
    db.delete(document)
    db.commit()

    if stored_filename:
        file_path = os.path.join(UPLOAD_DIR, stored_filename)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass

    return {"id": document_id, "message": "Belge, parçaları ve dosyası kalıcı olarak silindi."}


@router.patch("/{document_id}/visibility")
def update_document_visibility(document_id: str, payload: DocumentVisibilityUpdate, db: Session = Depends(get_db)):
    """Belgenin kapsamını değiştirir: 'internal' yalnızca çalışanlara, 'public' herkese cevap kaynağı olur.
    Yeniden indeksleme gerekmez; arama anında belge üzerinden filtrelenir."""
    document = _get_document_or_404(document_id, db)
    document.visibility = payload.visibility
    db.commit()
    return {"id": str(document.id), "visibility": document.visibility, "message": "Görünürlük güncellendi"}


@router.get("")
def list_documents(
    status: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    visibility: Optional[Literal["internal", "public"]] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    if company_id:
        query = query.filter(Document.company_id == company_id)
    if visibility:
        query = query.filter(Document.visibility == visibility)
    documents = query.order_by(Document.created_at.desc()).all()
    return [_serialize(d) for d in documents]


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document_or_404(document_id, db)
    return _serialize(document, detail=True)


@router.patch("/{document_id}")
def update_document_text(document_id: str, payload: DocumentTextUpdate, db: Session = Depends(get_db)):
    document = _get_document_or_404(document_id, db)
    if document.status == DocumentStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Onaylanmış bir dokümanın metni değiştirilemez")
    if document.status != DocumentStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"Bu durumdaki dokümanın metni düzenlenemez: {document.status}")

    document.raw_extracted_text = payload.raw_extracted_text
    db.commit()

    return {"id": str(document.id), "message": "Metin güncellendi"}
