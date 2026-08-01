import os
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

LLM_MODEL = os.getenv("LLM_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL")
CONTEXT_SIZE = int(os.getenv("CONTEXT_SIZE", 4096))

client = ollama.Client(host=OLLAMA_HOST)

# Sahte bir İK dokümanı parçası
SAHTE_BAGLAM = """
İzin Politikası:
Çalışanlar işe başladıktan 1 yıl sonra yıllık izin hakkı kazanır.
1-5 yıl arası kıdemi olan çalışanlar 14 gün, 5 yıl üzeri kıdemi olan çalışanlar 20 gün yıllık izin kullanabilir.
İzin talepleri en az 3 iş günü önceden İK sistemine girilmelidir.
"""

SISTEM_PROMPTU = f"""Sen bir şirketin İK asistanısın. Çalışanlara nazik, profesyonel ve kısa bir dille cevap veriyorsun.
Sadece aşağıdaki dokümanda yer alan bilgiyi kullanarak cevap ver. Dokümanda olmayan bir konu sorulursa,
UYDURMA CEVAP VERME — bunun yerine "Bu konuda elimde net bir bilgi yok, talebinizi İK ekibimize ilettim" de.

DOKÜMAN:
{SAHTE_BAGLAM}
"""

test_sorulari = [
    "Yıllık izin hakkım ne zaman başlıyor?",  # Dokümanda VAR
    "3 yıldır burada çalışıyorum, kaç gün iznim var?",  # Dokümanda VAR (biraz çıkarım gerektiriyor)
    "Doğum izni kaç gün?",  # Dokümanda YOK — halüsinasyon yapmamalı
]

def main():
    print(f"Model: {LLM_MODEL}\n")
    for soru in test_sorulari:
        response = client.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SISTEM_PROMPTU},
                {"role": "user", "content": soru},
            ],
            options={"num_ctx": CONTEXT_SIZE}
        )
        print(f"SORU: {soru}")
        print(f"CEVAP: {response['message']['content']}")
        print("-" * 60)

if __name__ == "__main__":
    main()
