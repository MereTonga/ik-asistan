import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
    chunks = chunk_text("")
    assert chunks == []


def test_chunk_text_strips_whitespace():
    text = "   Baştan ve sondan boşluklu, yeterince uzun bir paragraf.   \n\n"
    chunks = chunk_text(text)
    assert chunks[0] == chunks[0].strip()
