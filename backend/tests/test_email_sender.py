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

    sender.send_reply(
        to_address="test@example.com",
        subject="Re: Zaten Yanıt",
        body="Gövde",
    )

    captured = capsys.readouterr()
    assert "Re: Re:" not in captured.out
    assert "Konu: Re: Zaten Yanıt" in captured.out
