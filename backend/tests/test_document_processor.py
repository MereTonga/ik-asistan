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
