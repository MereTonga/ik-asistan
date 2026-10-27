import os
import imapclient
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")


def main():
    print(f"Bağlanılıyor: {IMAP_SERVER} ({EMAIL_ADDRESS})")
    server = imapclient.IMAPClient(IMAP_SERVER, ssl=True)
    server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
    print("✅ Giriş başarılı.")

    server.select_folder("INBOX", readonly=True)
    messages = server.search(["ALL"])
    print(f"Gelen kutusunda toplam {len(messages)} mail var.")

    server.logout()


if __name__ == "__main__":
    main()
