import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.email_service.sender import send_reply

send_reply(
    to_address="test@example.com",
    subject="İzin hakkım hakkında soru",
    body="Merhaba, yıllık izin hakkınız işe başladıktan 1 yıl sonra başlar.",
    in_reply_to_message_id="<test-message-id@example.com>",
)
