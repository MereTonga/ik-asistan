import codecs
import email
import email.utils
import re
from email.header import decode_header
from email.message import Message
from html.parser import HTMLParser

import imapclient

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

EMAIL_ADDRESS = settings.EMAIL_ADDRESS
EMAIL_APP_PASSWORD = settings.EMAIL_APP_PASSWORD
IMAP_SERVER = settings.IMAP_SERVER

_QUOTE_PATTERNS = [
    r"\n_{5,}\nGönderen:.*",           # Outlook (Türkçe)
    r"\nFrom:.*Sent:.*",                # Outlook (İngilizce, tek satırda)
    r"\nOn .* wrote:\n",                # Gmail/genel İngilizce
    r"\n-{2,}\s*Original Message\s*-{2,}.*",  # Genel "Original Message" bloğu
]

_MESSAGE_ID_RE = re.compile(r"<[^<>\s]+>")

# RFC 3834 / yaygın istemci başlıkları: bunlar oto-yanıt, bounce ya da liste mailidir, cevaplanmaz.
_AUTO_PRECEDENCE = {"bulk", "list", "junk", "auto_reply"}
_NOREPLY_PREFIXES = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "do_not_reply")
_SYSTEM_LOCALPARTS = {"mailer-daemon", "postmaster"}


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


def _safe_decode(payload: bytes, charset: str | None) -> str:
    """Bilinmeyen ya da bozuk charset'te patlamaz: verilen charset → utf-8 → latin-1 sırasıyla dener."""
    for encoding in (charset, "utf-8"):
        if not encoding:
            continue
        try:
            codecs.lookup(encoding)
        except LookupError:
            continue
        try:
            return payload.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("latin-1", errors="replace")


def _decode_mime_words(raw: str | None) -> str:
    """Konu başlığı gibi alanlar bazen kodlanmış (=?UTF-8?...) gelir, düz metne çevirir.
    Bilinmeyen kodlamada hata fırlatmak yerine okunabilir en iyi sonucu döner."""
    if not raw:
        return ""
    try:
        decoded_parts = decode_header(raw)
    except Exception:
        return " ".join(str(raw).split())
    pieces = []
    for part, encoding in decoded_parts:
        pieces.append(_safe_decode(part, encoding) if isinstance(part, bytes) else part)
    return " ".join("".join(pieces).split())


class _HTMLTextExtractor(HTMLParser):
    """Yalnızca text/html gövdesi olan maillerden düz metin çıkarır (ek bağımlılık yok)."""

    _BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table"}
    _SKIP_TAGS = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line).strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return parser.text()


def _extract_body(msg: Message) -> str:
    """Mailin gövdesini düz metin olarak çıkarır. text/plain varsa onu, yoksa text/html'i
    etiketlerden arındırarak kullanır. Ekler atlanır."""
    text_plain: str | None = None
    text_html: str | None = None

    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        if "attachment" in str(part.get("Content-Disposition", "")).lower():
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        decoded = _safe_decode(payload, part.get_content_charset())
        if content_type == "text/plain" and text_plain is None:
            text_plain = decoded
        elif content_type == "text/html" and text_html is None:
            text_html = decoded

    if text_plain and text_plain.strip():
        return text_plain
    if text_html:
        return _html_to_text(text_html)
    return text_plain or ""


def _normalize_message_id(raw) -> str | None:
    """Katlanmış (birden çok satıra bölünmüş) başlığı açar, '<...>' biçimindeki kimliği döner."""
    if not raw:
        return None
    flat = " ".join(str(raw).split())
    match = _MESSAGE_ID_RE.search(flat)
    return match.group(0) if match else (flat or None)


def _parse_references(raw) -> list[str]:
    if not raw:
        return []
    return _MESSAGE_ID_RE.findall(" ".join(str(raw).split()))


def detect_auto_reply(msg: Message, from_address: str) -> str | None:
    """Mail bir oto-yanıt, teslim raporu, liste maili ya da sistem adresinden geliyorsa
    sebebini döner; cevaplanabilir normal bir mailse None."""
    auto_submitted = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto_submitted and auto_submitted.split(";")[0].strip() != "no":
        return f"Auto-Submitted: {auto_submitted}"

    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in _AUTO_PRECEDENCE:
        return f"Precedence: {precedence}"

    if msg.get("X-Auto-Response-Suppress"):
        return "X-Auto-Response-Suppress"
    if msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return "X-Autoreply"
    if msg.get("List-Id") or msg.get("List-Unsubscribe"):
        return "liste maili"
    if msg.get_content_type() == "multipart/report":
        return "teslim raporu (bounce)"

    sender = (from_address or "").lower()
    local_part = sender.split("@")[0]
    if local_part in _SYSTEM_LOCALPARTS or local_part.startswith(_NOREPLY_PREFIXES):
        return f"sistem adresi: {sender}"
    if sender and sender == EMAIL_ADDRESS.lower():
        return "kendi adresimiz"
    return None


def parse_headers(raw: bytes, uid: int | None = None) -> dict:
    """Yalnızca başlıklardan (BODY.PEEK[HEADER]) karar için gereken alanları çıkarır; gövde yoktur."""
    msg = email.message_from_bytes(raw)
    from_address = email.utils.parseaddr(msg.get("From", ""))[1].strip()
    return {
        "uid": uid,
        "message_id": _normalize_message_id(msg.get("Message-ID")),
        "in_reply_to": _normalize_message_id(msg.get("In-Reply-To")),
        "references": _parse_references(msg.get("References")),
        "from_address": from_address,
        "subject": _decode_mime_words(msg.get("Subject", "")),
        "auto_reply_reason": detect_auto_reply(msg, from_address),
    }


def parse_email(raw: bytes, uid: int | None = None) -> dict:
    """Tam mesajı (BODY.PEEK[]) ayrıştırır: başlıklar + temizlenmiş gövde."""
    data = parse_headers(raw, uid)
    msg = email.message_from_bytes(raw)
    data["body"] = _strip_quoted_reply(_extract_body(msg))
    return data


class ImapInbox:
    """Tek bir IMAP oturumu: okunmamışları listele, başlık/gövde çek, işlenenleri işaretle.

    Hiçbir mail otomatik olarak 'okundu' olmaz (BODY.PEEK); yalnızca mark_processed()
    çağrıldığında \\Seen (ve İK'ya yönlendirilenlerde \\Flagged = yıldız) eklenir.
    """

    def __init__(self):
        self._server: imapclient.IMAPClient | None = None
        self.uidvalidity: int | None = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _connect(self):
        self._server = imapclient.IMAPClient(IMAP_SERVER, ssl=True)
        self._server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        info = self._server.select_folder("INBOX")
        self.uidvalidity = int(info.get(b"UIDVALIDITY", 0) or 0)

    def close(self):
        if self._server is not None:
            try:
                self._server.logout()
            except Exception:
                pass
            self._server = None

    def list_unseen_uids(self) -> list[int]:
        return list(self._server.search(["UNSEEN"]))

    def fetch_headers(self, uids: list[int]) -> dict[int, bytes]:
        if not uids:
            return {}
        response = self._server.fetch(uids, ["BODY.PEEK[HEADER]"])
        return {uid: data[b"BODY[HEADER]"] for uid, data in response.items() if b"BODY[HEADER]" in data}

    def fetch_message(self, uid: int) -> bytes:
        return self._server.fetch([uid], ["BODY.PEEK[]"])[uid][b"BODY[]"]

    def synthetic_message_id(self, uid: int) -> str:
        """Message-ID başlığı olmayan mailler için kararlı, benzersiz bir kimlik (idempotency için)."""
        return f"<imap-{self.uidvalidity or 0}-{uid}@ik-asistan.local>"

    def mark_processed(self, uid: int, flagged: bool = False) -> None:
        flags = [imapclient.SEEN] + ([imapclient.FLAGGED] if flagged else [])
        try:
            self._server.add_flags([uid], flags)
        except Exception as e:
            # Uzun süren LLM beklemesi sırasında sunucu bağlantıyı kapatmış olabilir: bir kez yeniden bağlan.
            logger.warning(f"IMAP işaretleme başarısız (uid={uid}): {e}; yeniden bağlanılıyor")
            self.close()
            self._connect()
            self._server.add_flags([uid], flags)


def fetch_unseen_emails() -> list[dict]:
    """Gelen kutusundaki okunmamış maillerin tamamını ayrıştırılmış olarak döner.
    Hiçbirini 'okundu' olarak İŞARETLEMEZ (tanı/smoke amaçlı; asıl akış check_new_emails_task)."""
    with ImapInbox() as inbox:
        uids = inbox.list_unseen_uids()
        return [parse_email(inbox.fetch_message(uid), uid) for uid in uids]
