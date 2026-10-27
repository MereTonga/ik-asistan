import os
import re
import pdfplumber
import ollama

from app.config import settings

OCR_MODEL = settings.OCR_MODEL
VL_MODEL = settings.VL_MODEL

client = ollama.Client(host=settings.OLLAMA_BASE_URL)

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

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_SENTENCE_END_RE = re.compile(r"[.!?:;]\s")


def _split_blocks(text: str) -> list[tuple[str | None, str]]:
    """Metni (başlık, gövde) bloklarına ayırır.
    Blok sınırı: boş satır ya da Markdown başlığı. Başlık, kendisinden sonraki
    blokların başına eklenir ki her chunk bağlamını taşısın."""
    blocks: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            blocks.append((heading, body))
        buffer.clear()

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _HEADING_RE.match(line):
            flush()
            heading = line.strip()
        elif not line.strip():
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def _cut_point(segment: str, max_chars: int) -> int:
    """`segment[:max_chars]` içinde mümkünse bir satır/cümle sonunda kesilecek konumu döner."""
    window = segment[:max_chars]
    newline = window.rfind("\n")
    if newline >= max_chars // 2:
        return newline + 1
    sentence_ends = [m.end() for m in _SENTENCE_END_RE.finditer(window)]
    if sentence_ends and sentence_ends[-1] >= max_chars // 2:
        return sentence_ends[-1]
    space = window.rfind(" ")
    if space >= max_chars // 2:
        return space + 1
    return max_chars


def _window(body: str, max_chars: int, overlap: int) -> list[str]:
    """Uzun bir gövdeyi en fazla max_chars uzunlukta, `overlap` kadar örtüşen pencerelere böler."""
    pieces: list[str] = []
    start = 0
    while start < len(body):
        remaining = body[start:]
        if len(remaining) <= max_chars:
            pieces.append(remaining.strip())
            break
        cut = _cut_point(remaining, max_chars)
        pieces.append(remaining[:cut].strip())
        # Bir sonraki pencere, bağlam kopmasın diye `overlap` kadar geriden başlar
        start += max(cut - overlap, 1)
    return [p for p in pieces if p]


def chunk_text(text: str, min_length: int = 20, max_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Metni RAG için chunk'lara ayırır.

    1) Boş satırlar ve Markdown başlıkları blok sınırıdır (OCR çıktısı başlıklı Markdown üretir).
    2) max_chars'tan uzun bloklar satır/cümle sonlarında kesilerek `overlap` örtüşmeli
       pencerelere bölünür. pdfplumber çıktısı gibi hiç boş satır içermeyen metinler de
       böylece tek dev chunk olmaktan kurtulur.
    3) Her chunk'ın başına bağlı olduğu başlık eklenir (varsa).
    4) min_length'ten kısa parçalar elenir.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    for heading, body in _split_blocks(text):
        prefix = f"{heading}\n\n" if heading else ""
        budget = max(max_chars - len(prefix), max_chars // 2)
        for piece in _window(body, budget, overlap):
            chunks.append(prefix + piece)

    return [c for c in chunks if len(c) >= min_length]


def get_embedding(text: str) -> list[float]:
    response = client.embed(model=settings.EMBEDDING_MODEL, input=text)
    return response["embeddings"][0]