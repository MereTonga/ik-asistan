import os
import pdfplumber
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")
OCR_MODEL = os.getenv("OCR_MODEL")
VL_MODEL = os.getenv("VL_MODEL")

client = ollama.Client(host=OLLAMA_HOST)

OCR_PROMPT = """Bu görseldeki metni oku ve Markdown formatında düzenli bir şekilde yaz.
Başlıkları # ile, alt başlıkları ## ile işaretle.
Eğer bir tablo varsa Markdown tablo formatında (| ile) yaz.
Sadece görseldeki içeriği yaz, yorum ekleme."""


def _pdf_has_text_layer(file_path: str) -> tuple[bool, str]:
    """PDF'in metin katmanı olup olmadığını kontrol eder.
    Varsa (True, çıkarılan_metin) döner, yoksa (False, "") döner."""
    with pdfplumber.open(file_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    # Anlamlı miktarda metin yoksa (örn. taranmış ama OCR katmanı olmayan PDF),
    # metin katmanı yok kabul ediyoruz
    has_layer = len(full_text.strip()) > 20
    return has_layer, full_text


def _run_ocr(file_path: str, model_name: str) -> str:
    response = client.chat(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": OCR_PROMPT,
                "images": [file_path],
            }
        ],
    )
    return response["message"]["content"]


def process_document(file_path: str, document_quality: str | None = None) -> dict:
    """
    Faz 0'daki karar ağacını uygular.
    document_quality: dosya bir görselse 'clean' ya da 'complex' olmalı, PDF'te kullanılmaz.
    Dönüş: {"source_type": ..., "extracted_text": ...}
    """
    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":
        has_layer, text = _pdf_has_text_layer(file_path)
        if has_layer:
            return {"source_type": "pdf_text", "extracted_text": text}
        else:
            # Metin katmanı olmayan (taranmış) bir PDF - şimdilik desteklemiyoruz,
            # ileride sayfaları görsele çevirip OCR'a vermek gerekebilir (ileri faz notu)
            raise ValueError("Bu PDF'te metin katmanı yok, henüz desteklenmiyor.")

    elif extension in (".jpg", ".jpeg", ".png"):
        if document_quality == "clean":
            text = _run_ocr(file_path, OCR_MODEL)
            return {"source_type": "ocr_clean", "extracted_text": text}
        elif document_quality == "complex":
            text = _run_ocr(file_path, VL_MODEL)
            return {"source_type": "ocr_complex", "extracted_text": text}
        else:
            raise ValueError("Görsel dosyalar için document_quality 'clean' ya da 'complex' olmalı.")

    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {extension}")
