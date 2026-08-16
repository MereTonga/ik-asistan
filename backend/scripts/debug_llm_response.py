import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

client = ollama.Client(host=os.getenv("OLLAMA_BASE_URL"))

# Buraya psql'den bulduğun GERÇEK soru metnini yapıştır (aynen, kısaltmadan)
SORU_METNI = """BURAYA_PSQL_CIKTISINI_YAPISTIR"""

response = client.chat(
    model=os.getenv("LLM_MODEL"),
    messages=[
        {"role": "system", "content": "Sen bir İK asistanısın. Kısa, net cevap ver."},
        {"role": "user", "content": SORU_METNI},
    ],
    options={"num_ctx": int(os.getenv("CONTEXT_SIZE", 4096))},
)

print("TAM YANIT (ham):")
print(json.dumps(response, indent=2, default=str, ensure_ascii=False))
