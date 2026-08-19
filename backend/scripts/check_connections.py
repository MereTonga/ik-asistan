import json
import os
import sys
import urllib.request
from dotenv import load_dotenv

# .env dosyasını proje kök dizininden yükle
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

def check_ollama():
    try:
        import ollama
        client = ollama.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        models = client.list()
        names = [m.get("model", m.get("name")) for m in models.get("models", [])]
        print(f"✅ Ollama bağlantısı OK. Kurulu modeller: {names}")
        return True
    except Exception as e:
        print(f"❌ Ollama bağlantısı BAŞARISIZ: {e}")
        return False

def check_postgres():
    try:
        import psycopg2
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
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL"))
        r.ping()
        print("✅ Redis bağlantısı OK.")
        return True
    except Exception as e:
        print(f"❌ Redis bağlantısı BAŞARISIZ: {e}")
        return False

def check_fastapi():
    """FastAPI /health endpoint'ini ve dönen JSON verisini kontrol eder."""
    api_url = "http://127.0.0.1:8000/health"
    try:
        req = urllib.request.Request(
            api_url, headers={"User-Agent": "HealthCheck"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "healthy":
                    print(f"✅ FastAPI Sunucusu OK ({api_url} -> status: healthy).")
                    return True
                else:
                    print(f"⚠️ FastAPI Beklenmeyen Yanıt: {data}")
                    return False
            else:
                print(f"❌ FastAPI HTTP Hatası: Kod {resp.status}")
                return False
    except Exception as e:
        print(f"❌ FastAPI Sunucusu ULAŞILAMAZ ({api_url}): {e}")
        return False


def check_nextjs():
    """Next.js ana sayfasına erişimi ve temel HTML yanıtını kontrol eder."""
    frontend_url = "http://127.0.0.1:5300"
    try:
        req = urllib.request.Request(
            frontend_url, headers={"User-Agent": "HealthCheck"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="ignore").lower()
                if "<html" in body or "<!doctype html" in body:
                    print(f"✅ Next.js Sunucusu OK ({frontend_url}).")
                    return True
                else:
                    print("⚠️ Next.js Beklenmeyen Yanıt: HTML içeriği bulunamadı.")
                    return False
            else:
                print(f"❌ Next.js HTTP Hatası: Kod {resp.status}")
                return False
    except Exception as e:
        print(f"❌ Next.js Sunucusu ULAŞILAMAZ ({frontend_url}): {e}")
        return False


def check_celery_worker():
    """Celery worker'larına ping atarak canlı olup olmadıklarını kontrol eder."""
    try:
        # Backend uygulamanızın celery nesnesini çağırır
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from app.celery_app import celery_app

        insp = celery_app.control.inspect(timeout=2.0)
        pings = insp.ping()
        if pings:
            workers = list(pings.keys())
            print(f"✅ Celery Worker OK. Aktif worker(lar): {workers}")
            return True
        else:
            print("❌ Celery Worker BAŞARISIZ: Hiçbir aktif worker ping yanıtı vermedi.")
            return False
    except Exception as e:
        print(f"❌ Celery Worker kontrolü BAŞARISIZ: {e}")
        return False


def check_celery_beat():
    """Celery Beat sürecinin çalışıp çalışmadığını PID / süreç listesi üzerinden kontrol eder."""
    import subprocess
    try:
        # beat sürecini sistem süreçlerinde arar
        out = subprocess.check_output(["pgrep", "-f", "celery.*beat"]).decode().strip()
        if out:
            pids = out.split("\n")
            print(f"✅ Celery Beat OK (Çalışan PID: {', '.join(pids)}).")
            return True
        else:
            print("❌ Celery Beat ÇALIŞMIYOR.")
            return False
    except subprocess.CalledProcessError:
        print("❌ Celery Beat ÇALIŞMIYOR (Süreç bulunamadı).")
        return False
    except Exception as e:
        print(f"❌ Celery Beat kontrol hatası: {e}")
        return False


if __name__ == "__main__":
    print("=" * 45)
    print("🔎 Sistem & Servis Bağlantı Kontrolleri")
    print("=" * 45)

    checks = [
        ("PostgreSQL", check_postgres),
        ("Redis", check_redis),
        ("Ollama", check_ollama),
        ("FastAPI", check_fastapi),
        ("Next.js", check_nextjs),
        ("Celery Worker", check_celery_worker),
        ("Celery Beat", check_celery_beat),
    ]

    results = []
    for name, check_fn in checks:
        results.append(check_fn())

    print("-" * 45)
    if all(results):
        print("🎉 TÜM SERVİSLER VE BAĞLANTILAR SORUNSUZ ÇALIŞIYOR!")
        sys.exit(0)
    else:
        print("⚠️ BAZI SERVİSLERDE SORUN TESPİT EDİLDİ.")
        sys.exit(1)