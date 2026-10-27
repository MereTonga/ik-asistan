import smtplib
from email.mime.text import MIMEText
from email.utils import make_msgid

from app.config import settings

EMAIL_ADDRESS = settings.EMAIL_ADDRESS
EMAIL_APP_PASSWORD = settings.EMAIL_APP_PASSWORD
SMTP_SERVER = settings.SMTP_SERVER
SMTP_PORT = settings.SMTP_PORT
EMAIL_DRY_RUN = settings.EMAIL_DRY_RUN  # pydantic bool: "true/1/yes/on" hepsi True sayılır


def build_reply_message(
    to_address: str,
    subject: str,
    body: str,
    in_reply_to_message_id: str | None = None,
    references: list[str] | None = None,
) -> MIMEText:
    """Cevap mailini oluşturur (gönderimden bağımsız, test edilebilir).

    - Otomatik yanıt olduğunu belirten standart başlıklar (RFC 3834 `Auto-Submitted`,
      `Precedence: bulk`, Exchange için `X-Auto-Response-Suppress`) eklenir; böylece
      karşı taraftaki tatil/oto-yanıt sistemleri bize tekrar cevap yazmaz (döngü koruması).
    - `References`, gelen mailin zincirine gelen mailin kendi kimliği eklenerek birikimli tutulur.
    """
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_address
    msg["Message-ID"] = make_msgid()
    msg["Auto-Submitted"] = "auto-replied"
    msg["Precedence"] = "bulk"
    msg["X-Auto-Response-Suppress"] = "All"

    if in_reply_to_message_id:
        msg["In-Reply-To"] = in_reply_to_message_id
        chain = [ref for ref in (references or []) if ref]
        if in_reply_to_message_id not in chain:
            chain.append(in_reply_to_message_id)
        msg["References"] = " ".join(chain)

    return msg


def build_hr_notification(
    hr_address: str,
    employee_address: str,
    subject: str,
    question: str,
    reason: str,
) -> MIMEText:
    """Yönlendirilen bir soruyu İK'nın ayrı adresine bildiren mail. `Reply-To` çalışanın adresi olduğu
    için İK "Yanıtla" dediğinde doğrudan çalışana yazar. Oto-yanıt başlıkları döngüyü önler."""
    body = (
        "Merhaba,\n\n"
        "İK Asistanı aşağıdaki soruyu otomatik cevaplayamadı ve çalışana 'talebiniz İK ekibimize iletildi' yanıtı gönderdi.\n\n"
        f"Çalışan: {employee_address}\n"
        f"Konu: {subject}\n"
        f"Neden yönlendirildi: {reason}\n\n"
        "Soru:\n"
        f"{question.strip()}\n\n"
        "Bu maili yanıtlarsanız cevabınız doğrudan çalışana gider.\n"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[İK Asistanı] Yönlendirilen soru: {subject}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = hr_address
    msg["Reply-To"] = employee_address
    msg["Message-ID"] = make_msgid()
    msg["Auto-Submitted"] = "auto-generated"
    msg["Precedence"] = "bulk"
    msg["X-Auto-Response-Suppress"] = "All"
    return msg


def send_hr_notification(hr_address: str, employee_address: str, subject: str, question: str, reason: str) -> str:
    """İK bildirimini gönderir (DRY_RUN'da yalnızca konsola yazar). Dönüş: Message-ID."""
    msg = build_hr_notification(hr_address, employee_address, subject, question, reason)

    if EMAIL_DRY_RUN:
        print("=" * 60)
        print("[DRY RUN] İK bildirimi GÖNDERİLMEDİ. İçerik:")
        print(f"Kime: {hr_address} (Reply-To: {employee_address})")
        print(f"Konu: {msg['Subject']}")
        print("=" * 60)
        return msg["Message-ID"]

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.send_message(msg)

    return msg["Message-ID"]


def send_reply(
    to_address: str,
    subject: str,
    body: str,
    in_reply_to_message_id: str | None = None,
    references: list[str] | None = None,
) -> str:
    """
    Bir cevap e-postası gönderir. DRY_RUN modundaysa göndermez, sadece konsola yazar.
    Dönüş: gönderilen (ya da üretilen) mesajın Message-ID'si.
    """
    msg = build_reply_message(to_address, subject, body, in_reply_to_message_id, references)
    new_message_id = msg["Message-ID"]

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
