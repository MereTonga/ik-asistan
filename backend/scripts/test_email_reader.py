import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.email_service.reader import fetch_unseen_emails

emails = fetch_unseen_emails()
if(len(emails) == 0):
    print("Okunmamış mail bulunamadı.")
else:
    print(f"{len(emails)} okunmamış mail bulundu.\n")
    for e in emails:
        print(f"Kimden: {e['from_address']}")
        print(f"Konu: {e['subject']}")
        print(f"Message-ID: {e['message_id']}")
        print(f"Gövde: {e['body']}")
    print("-" * 60)
