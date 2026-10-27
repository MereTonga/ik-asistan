import email

from app.email_service.reader import (
    _decode_mime_words,
    _extract_body,
    _normalize_message_id,
    _parse_references,
    _strip_quoted_reply,
    detect_auto_reply,
    parse_email,
    parse_headers,
)


def _raw(headers: str, body: str = "govde", content_type: str = "text/plain; charset=utf-8") -> bytes:
    return (
        f"From: Ali <ali@testcompany.com>\r\n{headers}Content-Type: {content_type}\r\n\r\n{body}"
    ).encode("utf-8")


# --- alıntı temizleme (Faz 8'den kalan regresyon testleri) -------------------

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
    assert _strip_quoted_reply(body) == body


def test_strip_quoted_reply_handles_unix_line_endings():
    body = "Yeni sorum.\n________________________________\nFrom: biri@example.com Sent: ..."
    assert "Yeni sorum." in _strip_quoted_reply(body)


# --- charset dayanıklılığı -----------------------------------------------------

def test_decode_mime_words_survives_unknown_charset():
    # Daha önce LookupError fırlatıp tüm poll'u durduruyordu
    assert _decode_mime_words("=?x-bogus?B?aGVsbG8=?=")  # patlamaz, bir şey döner
    assert _decode_mime_words("=?utf-8?B?xLB6aW4gc29ydXN1?=") == "İzin sorusu"
    assert _decode_mime_words(None) == ""


def test_extract_body_survives_unknown_charset_in_body():
    msg = email.message_from_bytes(_raw("", "merhaba", content_type="text/plain; charset=x-bogus"))
    assert _extract_body(msg) == "merhaba"


# --- HTML gövde ----------------------------------------------------------------

def test_html_only_single_part_mail_is_converted_to_text():
    raw = _raw("", "<html><body><p>İzin hakkım <b>ne zaman</b> başlıyor?</p><p>Teşekkürler</p></body></html>", content_type="text/html; charset=utf-8")
    data = parse_email(raw)
    assert data["body"] == "İzin hakkım ne zaman başlıyor?\nTeşekkürler"
    assert "<" not in data["body"]


def test_multipart_with_only_html_part_is_converted_to_text():
    raw = (
        b"From: ali@testcompany.com\r\nSubject: Soru\r\n"
        b"Content-Type: multipart/alternative; boundary=XX\r\n\r\n"
        b"--XX\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<div>Mesai <i>ucreti</i> nasil?</div><script>alert(1)</script>\r\n--XX--\r\n"
    )
    data = parse_email(raw)
    assert data["body"] == "Mesai ucreti nasil?"


def test_multipart_prefers_text_plain_and_skips_attachments():
    raw = (
        b"From: ali@testcompany.com\r\nSubject: Soru\r\n"
        b"Content-Type: multipart/mixed; boundary=XX\r\n\r\n"
        b"--XX\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Disposition: attachment; filename=\"not.txt\"\r\n\r\nEK ICERIGI\r\n"
        b"--XX\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>HTML surum</p>\r\n"
        b"--XX\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nAsil soru burada.\r\n"
        b"--XX--\r\n"
    )
    data = parse_email(raw)
    assert data["body"] == "Asil soru burada."


# --- başlık normalizasyonu -----------------------------------------------------

def test_folded_in_reply_to_header_is_normalized():
    raw = _raw("Subject: Re: Soru\r\nMessage-ID: <m2@x.com>\r\nIn-Reply-To:\r\n <bot123@gmail.com>\r\nReferences: <m1@x.com>\r\n <bot123@gmail.com>\r\n")
    data = parse_headers(raw, uid=5)
    assert data["in_reply_to"] == "<bot123@gmail.com>"
    assert data["references"] == ["<m1@x.com>", "<bot123@gmail.com>"]
    assert data["message_id"] == "<m2@x.com>"
    assert data["uid"] == 5


def test_normalize_message_id_and_references_helpers():
    assert _normalize_message_id("  <a@b>  ") == "<a@b>"
    assert _normalize_message_id(None) is None
    assert _parse_references("<a@b> <c@d>\r\n <e@f>") == ["<a@b>", "<c@d>", "<e@f>"]
    assert _parse_references(None) == []


def test_missing_message_id_is_none_so_task_can_synthesize():
    data = parse_headers(_raw("Subject: Soru\r\n"))
    assert data["message_id"] is None


# --- oto-yanıt tespiti ----------------------------------------------------------

def test_detect_auto_reply_variants():
    cases = {
        "Auto-Submitted: auto-replied\r\n": "Auto-Submitted",
        "Precedence: bulk\r\n": "Precedence",
        "X-Auto-Response-Suppress: All\r\n": "X-Auto-Response-Suppress",
        "List-Id: <liste.example.com>\r\n": "liste",
    }
    for header, expected in cases.items():
        data = parse_headers(_raw(header))
        assert data["auto_reply_reason"] and expected in data["auto_reply_reason"], header


def test_detect_auto_reply_accepts_normal_mail_and_auto_submitted_no():
    assert parse_headers(_raw("Subject: Normal\r\n"))["auto_reply_reason"] is None
    assert parse_headers(_raw("Auto-Submitted: no\r\n"))["auto_reply_reason"] is None


def test_detect_auto_reply_by_sender_address():
    msg = email.message_from_bytes(b"Subject: x\r\n\r\nbody")
    assert detect_auto_reply(msg, "MAILER-DAEMON@gmail.com")
    assert detect_auto_reply(msg, "noreply@sirket.com")
    assert detect_auto_reply(msg, "ali@sirket.com") is None


def test_detect_auto_reply_for_our_own_address(monkeypatch):
    import app.email_service.reader as reader_module

    monkeypatch.setattr(reader_module, "EMAIL_ADDRESS", "ik@sirket.com")
    msg = email.message_from_bytes(b"Subject: x\r\n\r\nbody")
    assert detect_auto_reply(msg, "IK@sirket.com") == "kendi adresimiz"
