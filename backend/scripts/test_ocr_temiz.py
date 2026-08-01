import os
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

OCR_MODEL = os.getenv("OCR_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")

# DİKKAT: dosya adını kendi test görselinle değiştir
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test_files/temiz_belge.jpg")

PROMPT = """Bu görseldeki metni oku ve Markdown formatında düzenli bir şekilde yaz.
Başlıkları # ile, alt başlıkları ## ile işaretle.
Eğer bir tablo varsa Markdown tablo formatında (| ile) yaz.
Sadece görseldeki içeriği yaz, yorum ekleme."""

def main():
    client = ollama.Client(host=OLLAMA_HOST)

    print(f"Model: {OCR_MODEL}")
    print(f"Görsel: {IMAGE_PATH}")
    print("İşleniyor, bekleyin...\n")

    response = client.chat(
        model=OCR_MODEL,
        messages=[
            {
                "role": "user",
                "content": PROMPT,
                "images": [IMAGE_PATH],
            }
        ],
    )

    print("--- MODEL ÇIKTISI ---\n")
    print(response["message"]["content"])
    print("\n--- BİTTİ ---")

if __name__ == "__main__":
    main()
