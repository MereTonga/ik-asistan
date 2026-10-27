from app.services.document_processor import chunk_text


def test_chunk_text_splits_on_double_newline():
    text = "Birinci paragraf burada yeterince uzun.\n\nİkinci paragraf da yeterince uzun."
    chunks = chunk_text(text)
    assert len(chunks) == 2


def test_chunk_text_filters_short_chunks():
    text = "Kısa\n\nBu paragraf minimum uzunluk şartını gerçekten karşılıyor."
    chunks = chunk_text(text)
    assert len(chunks) == 1  # "Kısa" elenmeli, min_length=20 altında


def test_chunk_text_empty_input_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_strips_whitespace():
    text = "   Baştan ve sondan boşluklu, yeterince uzun bir paragraf.   \n\n"
    chunks = chunk_text(text)
    assert chunks[0] == chunks[0].strip()


def test_chunk_text_prefixes_markdown_heading_to_every_chunk_under_it():
    text = (
        "# İzin Politikası\n"
        "Çalışanlar işe başladıktan 1 yıl sonra yıllık izin hakkı kazanır.\n\n"
        "İzin talepleri en az 3 iş günü önceden sisteme girilmelidir.\n\n"
        "## Mesai\n"
        "Fazla mesai yöneticinin onayıyla yapılır ve saat başı ücretlendirilir."
    )
    chunks = chunk_text(text)
    assert len(chunks) == 3
    assert chunks[0].startswith("# İzin Politikası\n\n")
    assert chunks[1].startswith("# İzin Politikası\n\n")
    assert chunks[2].startswith("## Mesai\n\n")
    assert "yıllık izin" in chunks[0] and "3 iş günü" in chunks[1]


def test_chunk_text_windows_long_block_without_blank_lines_like_pdfplumber_output():
    # pdfplumber çıktısı: satırlar tek \n ile ayrılır, hiç boş satır yoktur
    sentence = "Bu cümle bir politika belgesinden alınmış gibi görünen sıradan bir cümledir."
    lines = [f"{sentence} Satır {i}." for i in range(200)]
    text = "\n".join(lines)
    assert "\n\n" not in text and len(text) > 10000

    chunks = chunk_text(text, max_chars=1500, overlap=200)

    assert len(chunks) > 6
    assert all(len(c) <= 1500 for c in chunks)
    # Pencereler satır sonlarında kesilmeli (bir satırın ortasından değil)
    assert all(c.endswith(".") for c in chunks)
    # Örtüşme: bir sonraki chunk, öncekinin son satırını da taşımalı
    last_line_of_first = chunks[0].splitlines()[-1]
    assert last_line_of_first in chunks[1]
    # Hiçbir satır kaybolmamalı
    for i in range(200):
        assert any(f"Satır {i}." in c for c in chunks)


def test_chunk_text_windows_respect_heading_budget():
    body = " ".join(["Uzun bir paragraf cümlesi." for _ in range(300)])
    text = f"## Çok Uzun Bölüm\n{body}"

    chunks = chunk_text(text, max_chars=600, overlap=50)

    assert len(chunks) > 1
    assert all(c.startswith("## Çok Uzun Bölüm\n\n") for c in chunks)
    assert all(len(c) <= 600 for c in chunks)


def test_chunk_text_handles_windows_line_endings():
    text = "Birinci paragraf burada yeterince uzun.\r\n\r\nİkinci paragraf da yeterince uzun."
    assert len(chunk_text(text)) == 2


# --- Faz 17.0: OCR çıktı sağlık kontrolü ----------------------------------------

from unittest.mock import patch

from app.services.document_processor import assess_ocr_output


def test_assess_ocr_output_accepts_normal_turkish_text():
    text = (
        "# Yıllık İzin Politikası\n\n"
        "Çalışanlar işe başladıktan 1 yıl sonra yıllık izin hakkı kazanır. 1-5 yıl kıdemde 14 gün, "
        "5 yıl üzeri kıdemde 20 gün izin kullanılır.\n\n"
        "İzin talepleri en az 3 iş günü önceden sisteme girilir ve yönetici onayı gerekir."
    )
    assert assess_ocr_output(text) is None


def test_assess_ocr_output_rejects_prompt_echo_and_cjk_garbage():
    # Kullanıcının yazısız bir fotoğrafta gördüğü gerçek çıktı biçimi
    echo = "Eğer bir tablo varsa Markdown tablo formatında (| ile) yaz. Sadece görseldeki読む (| ile) yaz.静态\n" * 6
    cjk = "Eakter" + "伯生球" * 400
    assert "yönergeyi tekrar" in assess_ocr_output(echo)
    assert "Çince" in assess_ocr_output(cjk)


def test_assess_ocr_output_rejects_short_and_repetitive_output():
    assert "okunabilir metin" in assess_ocr_output("   ")
    assert "okunabilir metin" in assess_ocr_output("abc")
    repeated_lines = "\n".join(["Aynı satır burada tekrar ediyor"] * 12)
    assert "tekrar" in assess_ocr_output(repeated_lines)
    repeated_pattern = "ab " * 300
    assert "tekrar" in assess_ocr_output(repeated_pattern)


@patch("app.services.document_processor.client")
def test_run_ocr_raises_clear_error_on_garbage(mock_client, tmp_path):
    from app.services.document_processor import process_document

    image = tmp_path / "bos.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    mock_client.chat.return_value = {"message": {"content": "伯生球" * 200}}

    try:
        process_document(str(image), "clean")
    except ValueError as e:
        assert "OCR çıktısı güvenilir değil" in str(e)
        assert "yeniden işleyin" in str(e)
    else:
        raise AssertionError("ValueError bekleniyordu")


@patch("app.services.document_processor.client")
def test_run_ocr_passes_good_text_through(mock_client, tmp_path):
    from app.services.document_processor import process_document

    image = tmp_path / "belge.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    mock_client.chat.return_value = {"message": {"content": "# Mesai\n\nFazla mesai yöneticinin onayıyla yapılır ve saat başı ücretlendirilir."}}

    result = process_document(str(image), "complex")

    assert result["source_type"] == "ocr_complex"
    assert result["extracted_text"].startswith("# Mesai")


# --- Faz 21.0: metin dosyaları ----------------------------------------------------

def test_process_document_reads_markdown_and_text_directly(tmp_path):
    from app.services.document_processor import process_document

    md = tmp_path / "politika.md"
    md.write_text("﻿# İzin\n\nÇalışanlar 1 yıl sonra izin hakkı kazanır.", encoding="utf-8")
    txt = tmp_path / "not.txt"
    txt.write_text("Düz metin politika notu burada.", encoding="utf-8")
    empty = tmp_path / "bos.md"
    empty.write_text("   ", encoding="utf-8")

    md_result = process_document(str(md), None)
    txt_result = process_document(str(txt), "clean")  # kalite metin için yok sayılır

    assert md_result["source_type"] == "markdown_text"
    assert md_result["extracted_text"].startswith("# İzin")  # BOM temizlendi
    assert txt_result["source_type"] == "plain_text"
    try:
        process_document(str(empty), None)
    except ValueError as e:
        assert "boş" in str(e)
    else:
        raise AssertionError("ValueError bekleniyordu")
