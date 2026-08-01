import os
import sys
from dotenv import load_dotenv

# .env dosyasını proje kök dizininden yükle
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

def check_ollama():
    import ollama
    try:
        client = ollama.Client(host=os.getenv("OLLAMA_BASE_URL"))
        models = client.list()
        names = [m["model"] for m in models["models"]]
        print(f"✅ Ollama bağlantısı OK. Kurulu modeller: {names}")
        return True
    except Exception as e:
        print(f"❌ Ollama bağlantısı BAŞARISIZ: {e}")
        return False

def check_postgres():
    import psycopg2
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        conn.close()
        print("✅ PostgreSQL bağlantısı OK.")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL bağlantısı BAŞARISIZ: {e}")
        return False

def check_redis():
    import redis
    try:
        r = redis.from_url(os.getenv("REDIS_URL"))
        r.ping()
        print("✅ Redis bağlantısı OK.")
        return True
    except Exception as e:
        print(f"❌ Redis bağlantısı BAŞARISIZ: {e}")
        return False

if __name__ == "__main__":
    print("--- Bağlantı Kontrolleri Başlıyor ---")
    results = [check_ollama(), check_postgres(), check_redis()]
    print("--- Kontrol Bitti ---")
    if not all(results):
        sys.exit(1)  # bir sorun varsa script "başarısız" koduyla biter
