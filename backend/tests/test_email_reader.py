import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.email_service.reader import _strip_quoted_reply


def test_strip_quoted_reply_removes_outlook_turkish_quote():
    body = (
        "Bu benim gerçek sorum.\r\n"
        "________________________________\r\n"
        "Gönderen: biri@example.com\r\n"
        "Gönderildi: 1 Ocak 2026\r\n"
        "Konu: Test\r\n"
        "\r\n"
        "Bu eski cevaptı."
    )
    result = _strip_quoted_reply(body)
    assert result == "Bu benim gerçek sorum."
    assert "Gönderen:" not in result


def test_strip_quoted_reply_leaves_clean_body_untouched():
    body = "Alıntı bloğu olmayan, temiz bir soru."
    result = _strip_quoted_reply(body)
    assert result == body


def test_strip_quoted_reply_handles_unix_line_endings():
    # \r\n değil, sadece \n ile de çalışmalı
    body = "Yeni sorum.\n________________________________\nFrom: biri@example.com Sent: ..."
    result = _strip_quoted_reply(body)
    assert "Yeni sorum." in result
