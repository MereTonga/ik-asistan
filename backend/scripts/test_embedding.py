import os
import ollama
import numpy as np
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")

client = ollama.Client(host=OLLAMA_HOST)

def get_embedding(text: str):
    response = client.embed(model=EMBEDDING_MODEL, input=text)
    return np.array(response["embeddings"][0])

def cosine_similarity(vec1, vec2):
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

# Test grupları: (cümle1, cümle2, açıklama)
test_pairs = [
    (
        "Yıllık izin hakkım ne zaman başlıyor?",
        "İşe başladıktan kaç ay sonra izin kullanabilirim?",
        "Anlamca AYNI, farklı kelimelerle (YÜKSEK benzerlik beklenir)"
    ),
    (
        "Mesai ücreti nasıl hesaplanıyor?",
        "Ofiste kahve makinesi ne zaman bozuldu?",
        "Tamamen ALAKASIZ (DÜŞÜK benzerlik beklenir)"
    ),
    (
        "Uzaktan çalışma haftada kaç gün?",
        "Uzak bir şehirde çalışmak için ne yapmalıyım?",
        "Yüzeysel kelime benzerliği ama FARKLI anlam (ORTA/DÜŞÜK beklenir)"
    ),
]

def main():
    print(f"Model: {EMBEDDING_MODEL}\n")
    for text1, text2, aciklama in test_pairs:
        vec1 = get_embedding(text1)
        vec2 = get_embedding(text2)
        score = cosine_similarity(vec1, vec2)

        print(f"[{aciklama}]")
        print(f"  Cümle 1: {text1}")
        print(f"  Cümle 2: {text2}")
        print(f"  Benzerlik Skoru: {score:.4f}")
        print()

if __name__ == "__main__":
    main()
