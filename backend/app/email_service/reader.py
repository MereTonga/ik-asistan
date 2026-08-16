import re
import os
import email
from email.message import Message
from email.header import decode_header
import imapclient
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")

_QUOTE_PATTERNS = [
    r"\n_{5,}\nGönderen:.*",           # Outlook (Türkçe)
    r"\nFrom:.*Sent:.*",                # Outlook (İngilizce, tek satırda)
    r"\nOn .* wrote:\n",                # Gmail/genel İngilizce
    r"\n-{2,}\s*Original Message\s*-{2,}.*",  # Genel "Original Message" bloğu
]

def _strip_quoted_reply(body: str) -> str:
    """Bir cevap mailinde, e-posta istemcisinin otomatik eklediği
    'Gönderen/Sent/On ... wrote' bloklarını ve sonrasını keser."""
    # Windows tarzı satır sonlarını (\r\n) standart \n'e çeviriyoruz,
    # aksi halde regex desenleri Outlook gibi istemcilerde eşleşmiyor.
    body = body.replace("\r\n", "\n").replace("\r", "\n")

    for pattern in _QUOTE_PATTERNS:
        match = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
        if match:
            body = body[:match.start()]
    return body.strip()

def _decode_mime_words(raw: str) -> str:
    """Konu başlığı gibi alanlar bazen kodlanmış (=?UTF-8?...) gelir, düz metne çevirir."""
    decoded_parts = decode_header(raw)
    return "".join(
        part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
        for part, encoding in decoded_parts
    )


def _extract_body(msg: Message) -> str:
    """Mailin gövdesini (düz metin kısmını) çıkarır. Çok parçalı (multipart) mailleri destekler."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""

    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    return ""


def fetch_unseen_emails() -> list[dict]:
    """
    Gelen kutusundaki okunmamış mailleri çeker.

    Her mail için:
    message_id, in_reply_to, from_address, subject, body döner.

    Mailleri 'okundu' olarak İŞARETLEMEZ.
    """

    server = imapclient.IMAPClient(IMAP_SERVER, ssl=True)

    server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
    server.select_folder("INBOX")

    uids = server.search(["UNSEEN"])
    results = []

    for uid in uids:
        # raw_message = server.fetch([uid], ["RFC822"])[uid][b"RFC822"]
        raw_message = server.fetch([uid], ["BODY.PEEK[]"])[uid][b"BODY[]"]
        msg = email.message_from_bytes(raw_message)
        message_id_raw = msg.get("Message-ID")
        message_id = " ".join(message_id_raw.split()) if message_id_raw else None
        
        results.append({
            "uid": uid,
            "message_id": message_id,
            "in_reply_to": msg.get("In-Reply-To"),
            "from_address": email.utils.parseaddr(msg.get("From"))[1],
            "subject": _decode_mime_words(msg.get("Subject", "")),
            "body": _strip_quoted_reply(_extract_body(msg)),
        })

    server.logout()

    return results