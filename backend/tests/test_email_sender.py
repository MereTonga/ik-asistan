from app.email_service.sender import build_reply_message


def test_send_reply_dry_run_does_not_connect(monkeypatch, capsys):
    from app.email_service import sender

    monkeypatch.setattr(sender, "EMAIL_DRY_RUN", True)

    message_id = sender.send_reply(
        to_address="test@example.com",
        subject="Test Konu",
        body="Test gövde",
        in_reply_to_message_id="<orig@example.com>",
    )

    assert message_id  # bir Message-ID üretilmiş olmalı
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
    assert "GÖNDERİLMEDİ" in captured.out


def test_send_reply_does_not_double_prefix_re(monkeypatch, capsys):
    from app.email_service import sender

    monkeypatch.setattr(sender, "EMAIL_DRY_RUN", True)

    sender.send_reply(to_address="test@example.com", subject="Re: Zaten Yanıt", body="Gövde")

    captured = capsys.readouterr()
    assert "Re: Re:" not in captured.out
    assert "Konu: Re: Zaten Yanıt" in captured.out


def test_reply_message_carries_auto_reply_headers():
    msg = build_reply_message("a@b.com", "Soru", "Cevap")

    assert msg["Auto-Submitted"] == "auto-replied"
    assert msg["Precedence"] == "bulk"
    assert msg["X-Auto-Response-Suppress"] == "All"
    assert msg["Message-ID"].startswith("<")


def test_reply_message_accumulates_references():
    msg = build_reply_message(
        "a@b.com", "Soru", "Cevap",
        in_reply_to_message_id="<m3@x>",
        references=["<m1@x>", "<m2@x>"],
    )

    assert msg["In-Reply-To"] == "<m3@x>"
    assert msg["References"] == "<m1@x> <m2@x> <m3@x>"


def test_reply_message_without_in_reply_to_has_no_thread_headers():
    msg = build_reply_message("a@b.com", "Soru", "Cevap")
    assert msg["In-Reply-To"] is None
    assert msg["References"] is None


# --- Faz 17.2: İK bildirimi ----------------------------------------------------

def test_hr_notification_has_reply_to_employee_and_auto_headers(monkeypatch):
    from app.email_service import sender

    monkeypatch.setattr(sender, "EMAIL_ADDRESS", "ik@sirket.com")
    msg = sender.build_hr_notification(
        hr_address="ik.muduru@sirket.com",
        employee_address="ali@sirket.com",
        subject="Prim politikası",
        question="Prim ne zaman ödeniyor?",
        reason="belgelerde soruya yeterince benzer içerik bulunamadı",
    )

    assert msg["To"] == "ik.muduru@sirket.com"
    assert msg["Reply-To"] == "ali@sirket.com"
    assert msg["From"] == "ik@sirket.com"
    assert msg["Subject"].startswith("[İK Asistanı] Yönlendirilen soru:")
    assert msg["Auto-Submitted"] == "auto-generated"
    body = msg.get_payload(decode=True).decode("utf-8")
    assert "Prim ne zaman ödeniyor?" in body and "ali@sirket.com" in body and "benzer içerik" in body


def test_send_hr_notification_dry_run(monkeypatch, capsys):
    from app.email_service import sender

    monkeypatch.setattr(sender, "EMAIL_DRY_RUN", True)
    message_id = sender.send_hr_notification("ik.muduru@sirket.com", "ali@sirket.com", "Konu", "Soru", "neden")

    assert message_id
    assert "İK bildirimi GÖNDERİLMEDİ" in capsys.readouterr().out
