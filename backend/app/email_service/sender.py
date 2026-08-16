import os
import smtplib
from email.mime.text import MIMEText
from email.utils import make_msgid
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"


def send_reply(to_address: str, subject: str, body: str, in_reply_to_message_id: str | None = None) -> str:
    """
    Bir cevap e-postası gönderir. DRY_RUN modundaysa göndermez, sadece loglar.
    Dönüş: gönderilen (ya da üretilen) mesajın Message-ID'si.
    """
    new_message_id = make_msgid()

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_address
    msg["Message-ID"] = new_message_id

    if in_reply_to_message_id:
        msg["In-Reply-To"] = in_reply_to_message_id
        msg["References"] = in_reply_to_message_id

    if EMAIL_DRY_RUN:
        print("=" * 60)
        print("[DRY RUN] Gerçek mail GÖNDERİLMEDİ. İçerik:")
        print(f"Kime: {to_address}")
        print(f"Konu: {msg['Subject']}")
        print(f"Gövde:\n{body}")
        print("=" * 60)
        return new_message_id

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.send_message(msg)

    return new_message_id
