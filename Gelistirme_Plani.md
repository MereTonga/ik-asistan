# Geliştirme Planı ve Uygulama Rehberi

## Yapay Zeka Destekli Dijital İK E-Posta Asistanı

> **Bu dosya kimin için?** Bu doküman, projeyi bir insan geliştiricinin veya bir kod asistanının (Claude Code, Cursor, GitHub Copilot, Antigravity vb.) sıfırdan, sırayla uygulayabilmesi için yazılmıştır. Her fazda: ne yapılacağı, neden bu sırada yapıldığı, ve "bu faz bitti" diyebilmek için hangi kriterin sağlanması gerektiği (Definition of Done) belirtilmiştir. Genel mimari gerekçeleri ve teknoloji seçim detayları için bkz. `Proje_Dokumantasyonu.md`. Bu dosya, ondan farklı olarak **uygulama sırasına ve somut komutlara** odaklanır.

---

## 0. Kesinleşmiş Teknik Kararlar (Referans Tablosu)

Kod asistanları bu bölümü **değiştirmeden, sorgulamadan** referans almalı — bu kararlar önceki tartışmalarda gerekçeleriyle birlikte verilmiştir.

| Katman | Karar | Not |
|---|---|---|
| LLM (metin üretimi) | `qwen3.5:9b` (Ollama) | Kullanıcının 8GB VRAM (RTX 5060 Ti) sınırı nedeniyle 27b değil 9b. **Faz 1'de doğrulandı.** |
| Görsel/OCR (karmaşık belge) | `qwen3-vl:8b` (Ollama) | Eğik/bulanık/karmaşık fotoğraflar için. **Faz 1'de `4b` de test edildi ve reddedildi** (bkz. Faz 1 Sonuçları) — 8b'de kalınıyor, hız değil doğruluk önceliklendirildi. |
| OCR (temiz belge) | `glm-ocr` (Ollama) | 0.9B, çok hafif, OmniDocBench'te lider — düz taranmış belgeler için varsayılan. **Faz 1'de doğrulandı.** |
| PDF metin çıkarma | `pdfplumber` / `PyMuPDF` | Metin katmanlı (dijital) PDF'ler için — **AI kullanılmaz**, doğrudan çıkarma. **Faz 1'de %100 doğrulukla doğrulandı.** |
| Embedding | `qwen3-embedding:0.6b` (Ollama) | **Faz 1'de doğrulandı** — çıktı boyutu **1024** (`/api/tags` içindeki `embedding_length` alanından teyit edildi). Türkçe anlamsal ayrım net (bkz. Faz 1 Sonuçları). |
| LLM Context Uzunluğu | `num_ctx=4096` (`.env`'de `CONTEXT_SIZE`) | Varsayılan 16384 yerine — VRAM'e daha rahat sığması için (Faz 1'de test edildi, cevap kalitesi bozulmuyor) |
| Backend | FastAPI (Python) | Asenkron, AI kütüphaneleriyle doğal entegrasyon |
| Kuyruk | Celery + Redis | OCR/LLM gibi ağır işleri arka plana almak + periyodik görevler (örn. thread'leri otomatik `resolved` yapma) için |
| Veritabanı | PostgreSQL + `pgvector` | İlişkisel veri + vektör arama tek yerde. ChromaDB/MongoDB yerine tercih edildi — gerekçe için "Sık Sorulan Tasarım Soruları" bölümüne bakın. |
| RAG Orkestrasyonu | LangGraph | Koşullu dallanma (cevap üret / insana yönlendir) için |
| E-posta | Postmark veya SendGrid Inbound Parse | Webhook tabanlı gelen/giden e-posta |
| Frontend | Next.js + Tailwind + shadcn/ui | En son inşa edilir (Faz 7) |

### Belge İşleme Karar Ağacı (Faz 1-3'te kullanılacak mantık)

```
Belge geldi
   │
   ├─ Metin katmanlı PDF mi? ──► EVET ──► pdfplumber/PyMuPDF (AI yok)
   │
   └─ HAYIR (görsel/fotoğraf) ──► Yükleyen kişi "temiz" mi "karmaşık" mı seçti?
            │
            ├─ Temiz taranmış belge ──► glm-ocr
            └─ Karmaşık/fotoğraf ──► qwen3-vl:8b
```

### Sık Sorulan Tasarım Soruları (SSS)

Geliştirme sürecinde tekrar tekrar gündeme gelebilecek, önceden cevaplanmış kararlar:

- **"ChromaDB kullansak olmaz mıydı?"** Hayır — ChromaDB sadece vektör arama için tasarlanmış, şema-sız bir veritabanı; bizim `companies`/`documents`/`email_threads` gibi birbirine foreign key ile bağlı **ilişkisel** verimiz de var. İki ayrı veritabanı (biri ilişkisel, biri vektör) kurup senkron tutmak yerine, `pgvector` ile PostgreSQL'e vektör yeteneği ekleyip tek veritabanında kalıyoruz.
- **"MongoDB gibi bir NoSQL çözüm olmaz mıydı?"** Hayır — NoSQL, şeması sık değişen/esnek belge yapıları için güçlüdür. Bizim veri modelimiz tam tersi: sabit, öngörülebilir foreign key ilişkileri var (`Company → Document → DocumentChunk`, `EmailThread → Message`), ve `company_id` filtrelemesinin veritabanı seviyesinde garanti altına alınması (RLS ile) gerekiyor — bu, ilişkisel veritabanlarının güçlü olduğu bir alan.
- **"Embedding modeli iki metni karşılaştırıp mı vektör üretiyor?"** Hayır — embedding modeli **tek bir metni** alıp vektöre çevirir, karşılaştırma yapmaz. Karşılaştırma (cosine similarity), bizim kodumuzda veya `pgvector`'ün kendi mesafe operatörüyle (`<->`) ayrıca hesaplanır. Veritabanının rolü: doküman chunk'larının vektörlerini **önceden hesaplanmış halde saklamak**, böylece her e-postada 50 chunk'ı yeniden vektörleştirmek zorunda kalmayız — sadece gelen sorunun vektörünü hesaplayıp, veritabanındaki hazır vektörlerle karşılaştırırız.

---

## 1. Ortam Mimarisi (Windows / WSL2 Ayrımı)

| Konum | İçerik | Kurulum Türü |
|---|---|---|
| **Windows** | Ollama (tüm modellerle) | Native |
| **Windows** | (Eski) PostgreSQL | Dokunulmuyor, bu proje kullanmıyor |
| **WSL2 / Ubuntu** | Docker Desktop / Docker Engine | Native (tek native araç burada) |
| **WSL2 / Ubuntu** | Python 3.11+, venv | Native |
| **WSL2 / Ubuntu (Docker içinde)** | PostgreSQL + pgvector, Redis | Container — native kurulum değil |
| **WSL2 / Ubuntu** | Proje kod klasörü (`~/projects/ik-asistan`) | WSL2'nin kendi dosya sisteminde, **Windows tarafında değil** |

**Neden bu ayrım:** Ollama, GPU sürücü erişimi için Windows'ta native kalmalı. Proje kodu ve Docker Compose ise WSL2 dosya sisteminde olmalı — hem performans (Windows-WSL2 arası dosya erişimi yavaş) hem de gerçek üretim ortamına (Linux sunucu) yakınlık için. Köprü: WSL2 içindeki servisler Ollama'ya `http://host.docker.internal:11434` üzerinden ulaşır.

---

## FAZ 0 — Ortam Kurulumu

### Amaç
Hiçbir iş mantığı yazılmadan önce, tüm araçların birbiriyle konuştuğu, boş ama çalışan bir iskelet kurmak.

### Adımlar

**0.1 — Ollama modellerini Windows tarafında doğrula**
```powershell
ollama list
# Beklenen: qwen3.5:9b, qwen3-embedding:0.6b zaten mevcut
ollama pull qwen3-vl:8b
ollama pull glm-ocr
```

**0.2 — WSL2 + Ubuntu hazır olduğundan emin ol**
```powershell
wsl --status
wsl --list --verbose
```

**0.3 — Docker Desktop kurulumu ve WSL2 entegrasyonu**
- Docker Desktop kurulu değilse kur, Settings → Resources → WSL Integration'dan Ubuntu dağıtımını etkinleştir.

**0.4 — Proje klasörünü WSL2 dosya sisteminde oluştur**
```bash
# WSL2/Ubuntu terminalinde:
mkdir -p ~/projects/ik-asistan
cd ~/projects/ik-asistan
git init
```

> ⚠️ Kod asistanı için not: Projeyle ilgili hiçbir dosya `/mnt/c/...` altında oluşturulmamalı. Her zaman `~/projects/ik-asistan` (yani WSL2'nin kendi dosya sistemi) kullanılmalı.

**0.5 — Python ortamı**
```bash
python3 --version   # 3.11+ olmalı (3.12.3 ile doğrulandı)
# Ubuntu 24.04+ üzerinde venv modülü ayrıca kurulması gerekebilir:
sudo apt install python3.12-venv   # "ensurepip is not available" hatası alırsan bu adımı çalıştır
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard] sqlalchemy psycopg2-binary pgvector \
            celery redis python-dotenv pdfplumber pymupdf ollama langgraph numpy alembic
```

> Not: Sanal ortam klasörü adı olarak `.venv` kullanılıyor (gizli klasör, standart bir kural) — bundan sonraki tüm komutlarda `.venv/bin/activate` kullanılmalı.

**0.6 — `docker-compose.yml` (sadece altyapı servisleri — uygulama kodu değil)**
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ik_asistan
      POSTGRES_PASSWORD: dev_password_degistir
      POSTGRES_DB: ik_asistan_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

```bash
docker compose up -d
docker compose ps   # ikisi de "running" olmalı
```

**0.7 — `.env` dosyası ve `.gitignore`**
```env
DATABASE_URL=postgresql://ik_asistan:dev_password_degistir@localhost:5432/ik_asistan_db
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_MODEL=qwen3.5:9b
VL_MODEL=qwen3-vl:8b
OCR_MODEL=glm-ocr
EMBEDDING_MODEL=qwen3-embedding:0.6b
CONTEXT_SIZE=4096
```

`.gitignore` içeriği:
```
.env
.venv/
__pycache__/
*.pyc
```

**0.8 — Uçtan uca bağlantı doğrulaması (Faz 0'ın "bitti" kriteri)**

Aşağıdaki üç bağlantının **hepsi** başarılı olmadan Faz 1'e geçilmez:

```bash
# 1) WSL2'den Ollama'ya (Windows'ta çalışan) erişim testi
curl http://host.docker.internal:11434/api/tags

# 2) PostgreSQL bağlantı testi
docker exec -it ik-asistan-postgres-1 psql -U ik_asistan -d ik_asistan_db -c "SELECT 1;"

# 3) Redis bağlantı testi
docker exec -it ik-asistan-redis-1 redis-cli ping   # PONG dönmeli
```

Bu üçünü tek komutta kontrol etmek için `backend/scripts/check_connections.py` adında küçük bir health-check scripti de oluşturulmuştur — `.env`'i okuyup üç servisi de sırayla test eder, bir servis çökse bile diğerlerini kontrol etmeye devam eder (`try/except` ile). İleride bir servis bozulduğunda tek komutla (`python backend/scripts/check_connections.py`) hangi servisin sorunlu olduğunu hızlıca görmek için kullanılır.

### ⚠️ Bilinen Kurulum Sorunları ve Çözümleri

Bu proje kurulurken karşılaşılan ve çözülen sorunlar — aynı ortamı sıfırdan kuran biri (veya bir kod asistanı) aynı noktalarda takılabilir:

**1) Ollama'ya WSL2'den erişilemiyor (`curl` sonsuza kadar bekliyor / timeout veriyor):**
Sebep: Ollama varsayılan olarak sadece `127.0.0.1`'i (Windows'un kendi içini) dinler, WSL2'nin sanal ağından gelen istekleri hiç görmez.
Çözüm: Windows'ta **kullanıcı ortam değişkenlerine** `OLLAMA_HOST=0.0.0.0` ekle, Ollama'yı tamamen kapatıp yeniden başlat. `netstat -ano | findstr 11434` ile `0.0.0.0:11434` göründüğünü doğrula.
> ⚠️ Güvenlik notu: Bu değişiklik, Ollama'yı sadece WSL2'ye değil, **yerel ağdaki (Wi-Fi/LAN) diğer cihazlara da** açar (internete değil — bunun için ayrıca router port yönlendirmesi gerekir). Halka açık bir ağa (kafe, havaalanı) bağlanırken Ollama'yı kapatmak veya bu değişkeni geçici kaldırmak önerilir. Faz 8'de, sadece WSL2'nin IP aralığına izin veren bir Windows Firewall kuralıyla bu sıkılaştırılabilir.

**2) Docker container'ları sonsuza kadar "Starting" durumunda takılı kalıyor:**
Sebep: WSL2/Docker Desktop altyapısında geçici bir bozulma (kesin kök neden teşhis edilemedi, ama `docker info`'nun yanıt vermesine rağmen container'ların başlamaması bu duruma işaret eder).
Çözüm: Windows PowerShell'de `wsl --shutdown` çalıştır (bu, Docker Desktop'ın kendi gizli WSL dağıtımını da kapsayarak tüm WSL altyapısını sıfırlar), Docker Desktop'ı yeniden başlat, `docker compose up -d` tekrar dene.

### Önerilen Klasör Yapısı (sonraki fazlar için)
```
ik-asistan/
├── docker-compose.yml
├── .env
├── .gitignore
├── .venv/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── db/                # SQLAlchemy engine/session (Faz 2)
│   │   ├── models/            # SQLAlchemy modelleri (Faz 2)
│   │   ├── api/                # FastAPI router'ları (Faz 3)
│   │   ├── services/           # Ollama çağrıları, OCR/embedding sarmalayıcıları
│   │   ├── rag/                 # LangGraph akışı (Faz 4)
│   │   ├── tasks/               # Celery task'ları (Faz 5)
│   │   └── email/              # Webhook/gönderim mantığı (Faz 6)
│   ├── alembic/                 # Migration dosyaları (Faz 2)
│   └── scripts/                 # Faz 1'in izole test scriptleri + check_connections.py
└── frontend/                    # Next.js (Faz 7'de oluşturulacak)
```

### Faz 0 — Definition of Done
- [x] `qwen3.5:9b`, `qwen3-vl:8b`, `glm-ocr`, `qwen3-embedding:0.6b` Windows'ta `ollama list` çıktısında görünüyor
- [x] `docker compose up -d` ile Postgres ve Redis container'ları ayakta
- [x] WSL2'den `host.docker.internal:11434` üzerinden Ollama'ya `curl` isteği başarılı (`OLLAMA_HOST=0.0.0.0` gerekti)
- [x] `.venv` aktif, tüm Python paketleri hatasız kuruldu
- [x] Proje klasörü `~/projects/ik-asistan` altında, Windows tarafında hiçbir kopya yok
- [x] `check_connections.py` health-check scripti üç servisi de tek komutla doğrulayabiliyor

**Faz 0 tamamlandı.**

---

## FAZ 1 — Yapay Zeka Çekirdeğini İzole Şekilde Kanıtla

**Neden:** Framework/veritabanı yokken, temel varsayımları (OCR kalitesi, embedding'in Türkçe'de anlam yakalaması, LLM ton kalitesi) doğrula. Bu proje temelde bir AI ürünü — bu çalışmazsa geri kalanın önemi yok.

**Yapılacaklar** (`backend/scripts/` altında, framework kullanmadan, düz Python):
1. `test_ocr_temiz.py` → örnek taranmış bir belgeyi `glm-ocr`'a ver, Markdown çıktısını kontrol et.
2. `test_ocr_karmasik.py` → aynısını bir telefon fotoğrafıyla `qwen3-vl:8b`'ye yap.
3. `test_pdf_extraction.py` → dijital bir PDF ile `pdfplumber`'ın metni doğru çıkardığını doğrula.
4. `test_embedding.py` → birkaç Türkçe İK cümlesini `qwen3-embedding:0.6b` ile vektörleştir, benzer cümlelerin kosinüs benzerliğinin gerçekten yüksek çıktığını doğrula.
5. `test_llm_ton.py` → `qwen3.5:9b`'ye sahte bağlam + soru ver, cevap tonunu değerlendir.

### Faz 1 — Definition of Done
- [x] Her 5 script de çalışıyor ve çıktı gözle/elle değerlendirildi
- [x] Embedding modelinin Türkçe'de "yakın anlamlı cümleleri" gerçekten yakın skorladığı doğrulandı
- [x] `qwen3-vl:8b` ve `glm-ocr` VRAM'e sığıyor (kısmi CPU offload olsa da OOM hatası yok)

**Faz 1 tamamlandı.**

### Faz 1 Sonuçları (Bulgular Tablosu)

| Bileşen | Sonuç | Alınan Karar / Not |
|---|---|---|
| `glm-ocr` (temiz belge) | Başarılı, %100 GPU, hızlı (<1 dk) | Küçük ı/i okuma hataları var (Türkçe'ye özgü noktalı/noktasız-ı karışıklığı) — bazen anlam değiştirebiliyor (örn. "sıktı"→"siktı"). İK belgelerinde kritik kelimelere dikkat gerekir. |
| `qwen3-vl:8b` (karmaşık foto) | Başarılı ama %68 CPU'ya taşıyor, yavaş (~6-7 dk) | **Kabul edildi** — OCR nadir/toplu bir iş (gerçek zamanlı baskı yok), doğruluk hızdan daha önemli. |
| `qwen3-vl:4b` denemesi | Hızlı (%100 GPU, 2-3 dk) ama anlam bozan halüsinasyonlar üretiyor (özellikle e-posta adresi gibi kritik veride) | **Reddedildi.** 8b'de kalınıyor. |
| `pdfplumber` (dijital PDF) | %100 doğru | AI'sız yol tam çalışıyor, sürpriz yok. |
| `qwen3-embedding:0.6b` | Anlamsal ayrım net: aynı-anlam 0.69, alakasız 0.22, yüzeysel-benzer-ama-farklı-anlam 0.39 | 0.6b'de kalınıyor. RAG güven eşiği için **~0.5-0.6 civarı** ilk referans olarak not edildi (Faz 4'te gerçek verilerle kalibre edilecek). Embedding boyutu: **1024**. |
| `qwen3.5:9b` (LLM ton) | Doğru, tutarlı, halüsinasyon yok (dokümanda olmayan bilgide doğru şekilde "bilmiyorum" diyor) | `num_ctx=4096` ile GPU kullanımı %88'e çıktı (önceden %88 CPU'ya taşıyordu). Nadir bir yabancı karakter sızıntısı (`净`) gözlemlendi — alarm sebebi değil, tekrar ederse Faz 6'da bir "output sanitization" katmanı düşünülebilir. |

**Genel çıkarım — insan onay ekranı (Faz 7) için tasarım notu:** OCR hataları iki farklı kategoride: (1) kozmetik/cümle içi hatalar (fark edilmesi kolay), (2) e-posta/tarih/tutar/link gibi "tam eşleşmesi gereken" veride sessiz, akla yatkın ama yanlış üretim (fark edilmesi zor). Onay ekranında bu tür kritik alanların (regex ile tespit edilip) otomatik vurgulanması önerilir.

---

## FAZ 2 — Veritabanı Şeması

**Neden bu sırada:** Faz 1'de modellerin gerçek çıktı formatı (embedding boyutu = 1024, OCR'ın Markdown yapısı) netleşti — şema artık tahminle değil gerçek veriyle tasarlanır.

### Alt Adımlar ve Durum

- [x] **2.1** — SQLAlchemy + Alembic kurulumu, `.env` üzerinden veritabanı bağlantısı (`backend/app/db/session.py`, `backend/alembic/env.py`)
- [x] **2.2** — `Company` modeli (`backend/app/models/company.py`)
- [x] **2.3** — `Document` ve `DocumentChunk` modelleri (`backend/app/models/document.py`)
- [x] **2.4** — `EmailThread` ve `Message` modelleri (`backend/app/models/email.py`)
- [x] **2.5** — İlk Alembic migration'ının oluşturulup veritabanına uygulanması
- [x] **2.6** — `psql` üzerinden elle doğrulama + commit

### Model Tasarım Kararları (2.1-2.4'te alındı)

- **`id` alanları neden UUID, artan sayı (1,2,3...) değil:** Tahmin edilebilir ID'lerle başka bir şirketin verisine "ID enumeration" ile erişme riskini ortadan kaldırmak için — çok kiracılı sistemlerde standart bir güvenlik pratiği.
- **`company_id`, hem `Document`'ta hem `DocumentChunk`'ta tekrar ediliyor (bilinçli denormalizasyon):** Teknik olarak `DocumentChunk → Document → Company` zinciriyle de bulunabilirdi, ama en sık/en kritik sorgumuz ("bu company_id'ye ait chunk'lar arasında en yakını bul") için join gerektirmeyen doğrudan bir `company_id` kolonu hem performans hem de gelecekteki RLS (Row Level Security) uygulaması için daha uygun.
- **`status`/`source_type` gibi alanlar neden `String`, neden `Enum` değil:** Proje henüz erken/öğrenme aşamasında; yeni bir durum eklemek istendiğinde (örn. `"rejected"`) Enum kullansaydık ayrı bir migration gerekirdi. `String` ile esneklik korunuyor. **Faz 8'de** (sıkılaştırma), değerler netleştiğinde Enum'a geçiş değerlendirilebilir.
- **`root_message_id_header` (`EmailThread`):** E-postanın `Message-ID` başlığını tutar — Faz 6'da gelen bir mailin hangi thread'e ait olduğunu bulmak için birincil (en güvenilir) eşleştirme yöntemi.
- **Thread eşleştirme stratejisi (Faz 6 için tasarım kararı, şimdiden not edildi):** Kullanıcılar her zaman "Reply" kullanmaz, yeni bir e-posta olarak da yazabilirler. Bu durumda `Message-ID` eşleşmesi bulunamaz. Çözüm **iki katmanlı**: (1) Önce `Message-ID`/`In-Reply-To` ile kesin eşleştirme denenir. (2) Bulunamazsa, aynı `employee_email` + son N gün içinde açılmış + benzer `subject` (normalize edilip karşılaştırılan, hatta embedding ile benzerlik ölçülebilen) bir `open` thread aranır. Bu, %100 çözüm değildir (hiçbir destek/CRM sistemi bu sorunu tam çözemez) — makul bir yaklaşım olarak kabul edilmiştir.
- **Thread `resolved` durumuna otomatik geçiş (Faz 6 için tasarım kararı):** Bir insanın "teşekkürler" yazması beklenmez (güvenilir bir sinyal değil). Bunun yerine: Celery Beat ile **periyodik olarak** (örn. her gece) çalışan bir görev, `status='open'` olan thread'leri tarar; son mesajın üzerinden belirli bir süre (öneri: `.env`'de `THREAD_REOPEN_WINDOW_DAYS` adında bir parametre, başlangıç değeri örn. 5 gün) geçmişse `status='resolved'` yapar. Bu "gerçek memnuniyeti" ölçmez, sadece idari bir kapanıştır — gerçek memnuniyet ölçümü (örn. e-postaya "yardımcı oldu mu?" linki eklemek) MVP kapsamı dışında, ileri faz notu olarak bırakılmıştır.
- **Veri saklama süresi (KVKK notu):** E-posta/mesaj verisinin süresiz saklanması KVKK'nın "amaç için gerekli süre kadar saklama" ilkesiyle çelişebilir. Şu an (demo/tek kullanıcı aşamasında) bir saklama/silme politikası **uygulanmıyor** — gerçek ürün senaryosunda (Bölüm 11'deki genel KVKK maddesiyle birlikte) bir saklama süresi belirlenip otomatik arşivleme/anonimleştirme görevi eklenmesi gerektiği not edilmiştir.
- **Alembic autogenerate + `pgvector` uyumsuzluğu (bilinen sorun):** `alembic revision --autogenerate` komutu, `embedding` gibi `pgvector.sqlalchemy.Vector` tipi kolonlar içeren migration dosyalarını üretirken, gereken `import pgvector` satırını **otomatik eklemiyor** — dosya bu haliyle çalıştırılırsa `NameError` verir. Her yeni migration'da (embedding kolonuyla ilgili bir değişiklik varsa) dosyanın en üstüne elle `import pgvector` eklenmesi gerekiyor; migration çalıştırılmadan önce içeriğinin gözden geçirilmesi bu yüzden de önemli.

### Faz 2 — Definition of Done
- [x] `alembic upgrade head` hatasız çalışıyor
- [x] `document_chunks` tablosunda `pgvector` tipi kolon doğru boyutla (1024) tanımlı — `psql \d document_chunks` ile teyit edildi
- [x] `psql` ile tüm tablolar (`companies`, `documents`, `document_chunks`, `email_threads`, `messages`) elle doğrulandı (`\dt`), `vector` eklentisinin aktif olduğu doğrulandı (`\dx`)

**Faz 2 tamamlandı.**

---

## FAZ 3 — FastAPI + Senkron Ingestion Akışı

**Neden Celery olmadan önce:** İş mantığı (upload → sınıflandırma → OCR/PDF-extraction → onay → chunk → embedding) ile asenkron altyapıyı aynı anda debug etmemek için.

**Yapılacaklar:**
- `POST /documents/upload` — dosya türüne göre Faz 0'daki karar ağacını uygular
- `POST /documents/{id}/approve` — onay sonrası chunk'lama + embedding + DB kaydı

### Faz 3 — Definition of Done
- [ ] Swagger UI (`/docs`) üzerinden tam akış (upload → onay → DB'de chunk görünüyor) elle test edildi

---

## FAZ 4 — RAG Karar Mantığı (LangGraph)

**Neden e-postadan önce:** Sistemin "beynini" e-posta karmaşıklığı devrede değilken izole test etmek için.

**Yapılacaklar:**
- LangGraph state machine: soru → embedding → vektör arama (`company_id` filtreli) → skor eşiği → cevap üretimi veya escalation
- Terminal üzerinden elle soru girilerek test edilir (henüz e-posta yok)

### Faz 4 — Definition of Done
- [ ] Yüksek skorlu bir soru doğru cevaplanıyor
- [ ] Düşük skorlu / alakasız bir soru doğru şekilde "insana yönlendir" dalına düşüyor

---

## FAZ 5 — Celery + Redis Devreye Alma

**Neden bu sırada:** Mantık zaten Faz 3-4'te kanıtlandı; burada tek iş bunu arka plana taşımak.

**Yapılacaklar:**
- Faz 3'teki OCR/embedding işlemleri ve Faz 4'teki RAG akışı Celery task'larına sarılır

### Faz 5 — Definition of Done
- [ ] `celery -A app.tasks worker` çalışıyor, görevler kuyruğa düşüp işleniyor

---

## FAZ 6 — E-posta Entegrasyonu

**Revize mimari kararı (Faz 5 sonunda tartışılıp değiştirildi):** Postmark/SendGrid Inbound Parse yerine **kendi sunucumuzdan IMAP/SMTP ile doğrudan okuma** tercih edildi — gerekçe: projenin "lokal AI, veri dışarı çıkmıyor" değer önerisiyle tutarlılık (üçüncü parti bir e-posta servisinin araya girmesi bu hikayeyi zayıflatırdı). Kimlik doğrulama için **App Password** (OAuth2 değil — bkz. Bölüm 11 notu), webhook yerine **Celery Beat ile periyodik polling** kullanıldı.

**Tamamlanan alt adımlar:**
- [x] **6.1-6.2** — Gmail App Password ile IMAP/SMTP bağlantısı kuruldu, `.env`'e taşındı (`EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `IMAP_SERVER`, `SMTP_SERVER`, `EMAIL_DRY_RUN`, `EMAIL_POLL_INTERVAL_SECONDS`). `imapclient` bağımlılığı eklendi.
- [x] **6.3** — `app/email_service/reader.py`: `fetch_unseen_emails()` — IMAP `UNSEEN` araması + `BODY.PEEK[]` (okundu işaretlemeden okuma) + `email` modülü ile MIME parse.
- [x] **6.4** — `app/email_service/processor.py`: iki katmanlı thread eşleştirme (önce `In-Reply-To` ile kesin eşleştirme, bulunamazsa `employee_email` + normalize edilmiş `subject` + 30 günlük pencere ile sezgisel eşleştirme) ve gerçek idempotency (`Message.message_id_header`, DB seviyesinde `unique` kısıtlamalı).
- [x] **6.5** — `app/email_service/sender.py`: SMTP gönderim, `In-Reply-To`/`References` başlıklarıyla thread'e doğru yerleşme, `EMAIL_DRY_RUN` güvenlik anahtarı.
- [x] **6.6** — `app/tasks/email_tasks.py`: `check_new_emails_task` — oku → idempotency/şirket/thread kontrolü → RAG'a sor → cevapla → kaydet akışının tamamı.
- [x] **6.7** — Celery Beat ile periyodik zamanlama (`EMAIL_POLL_INTERVAL_SECONDS`), Redis tabanlı dağıtık kilit (`SET NX EX`) ile eşzamanlı çalışma (race condition) önlendi, her mail kendi `try/except`'i içinde işlenerek hata izolasyonu sağlandı.
- [x] **6.8** — Gerçek Gmail/Outlook hesapları arasında, 4 farklı senaryoyla (temiz soru, alıntılı takip sorusu, dokümanda olmayan konu, kıdem bazlı çıkarım gereken soru, karma/sınır durumu) uçtan uca doğrulandı.

**Yol boyunca bulunup düzeltilen gerçek sorunlar (öğretici, kayda değer):**
1. **IMAP `RFC822` fetch'in mail'i otomatik "okundu" işaretlemesi** → `BODY.PEEK[]` ile düzeltildi.
2. **Charset varsayımı (`utf-8` sabit)** Türkçe karakterleri sessizce siliyordu → `part.get_content_charset()` ile mailin kendi bildirdiği kodlama kullanılarak düzeltildi.
3. **Aynı e-postanın iki paralel `check_new_emails` çalıştırmasında çakışıp `UniqueViolation` hatası vermesi** (bir görev LLM'i beklerken ikinci poll'ün tetiklenmesi) → Redis `SET NX EX` ile dağıtık kilit eklendi.
4. **Kilidin `finally` bloğunda silinmeyi unutması** (iki ayrı kod parçası birleştirilirken bir satır kaybolmuştu) → tekrar gözden geçirilip düzeltildi; bu tür "sessiz" hataların kodun gerçek halini (`cat` ile) görmeden tahminle teşhis edilemeyeceği bir kez daha doğrulandı.
5. **Outlook/Gmail'in "Yanıtla" ile otomatik eklediği alıntı bloğunun (`Gönderen:/Sent:/On ... wrote:`) soru metnine karışması** → regex tabanlı `_strip_quoted_reply()` ile düzeltildi.
6. **Aynı düzeltmenin ilk denemede çalışmaması** — Outlook'un `\r\n` (Windows tarzı satır sonu) kullanması, `\n` bekleyen regex desenleriyle eşleşmiyordu → önce `\r\n`/`\r` → `\n` normalizasyonu eklenerek düzeltildi.

**Bilinen sınırlamalar (Bölüm 11'e eklenecek):**
- Alıntı temizleme (`_strip_quoted_reply`) regex tabanlı ve **%100 kapsayıcı değil** — farklı mail istemcilerinin formatları kaçabilir; gerçek üründe `talon` gibi özel bir kütüphaneye geçilmesi önerilir.
- Bilinmeyen domain'den gelen mailler şu an sessizce atlanıyor — bildirim/log mekanizması yok.
- `References` başlığı sadece son mesaj ID'sini taşıyor, standart gereği birikimli olması gerekirdi.
- App Password + Gmail ile sınırlı test edildi; OAuth2 ve farklı sağlayıcılar (Outlook/Exchange kurumsal IMAP) test edilmedi.
- **Domain eşleştirmesi "bir domain = bir şirket" varsayımına dayanıyor:** Gerçek dünyada çalışanlar/stajyerler/dış paydaşlar (staj deneyiminden gelen gerçek örnek: Koton'un kendi domain'i olsa da stajyer kişisel Outlook'undan yazabiliyor) kişisel mail adresleri kullanabiliyor — bu kişiler `unknown_domain` olarak atlanıp sistemle hiç iletişim kuramıyor. Gerçek çözüm: `company_id` + tam e-posta adresi tutan ayrı bir "yetkili gönderen" (`authorized_senders`/`employees`) tablosu eklenmesi gerekir — bu, ciddi bir şema/mantık genişlemesi olduğu için MVP kapsamına alınmadı, bilinçli bir sınırlama olarak bırakıldı.
- **Paylaşılan/genel domain riski:** Eğer küçük bir şirket kendi domain'i olmadığı için `email_domain` alanına `gmail.com`/`outlook.com` gibi paylaşılan bir domain kaydederse, o domain'deki **herhangi bir kullanıcı** yanlışlıkla o şirketin çalışanı sayılıp şirketin İK verisine erişebilir — bu, onboarding sürecinde (gerçek ürün senaryosunda) engellenmesi/uyarılması gereken bir veri sızıntısı riski.
- **"Her gelen mail bir İK sorusudur" varsayımı:** Sistem, gelen mailin niyetini (İK sorusu mu, iş başvurusu mu, spam mı, alakasız bir konu mu) sınıflandırmıyor — doğrudan RAG'a soruyor. Yanlış niyet sınıflandırması riski var; gerçek üründe bir "niyet tespiti" ön adımı gerekebilir, bu MVP kapsamının dışında bırakıldı.

**Faz 7 için not (kullanıcı önerisi):** Gerçek e-posta göndermeden test yapabilmek için `/test` adlı bir frontend bölümü ve `test_emails.json` üzerinden senaryo seçimi planlanıyor — bu, `check_new_emails_task`'ın IMAP okuma adımını atlayıp aynı iç mantığı (idempotency, thread eşleştirme, RAG, gönderim) doğrudan tetikleyen bir endpoint ile kod tekrarı olmadan uygulanabilir.

**Faz 6 tamamlandı.**

---

## FAZ 7 — Next.js Paneli

**Yapılacaklar:**
- OCR onay ekranı (orijinal görsel / Markdown yan yana)
- Belge yönetimi, analitik ekranı

### Faz 7 — Definition of Done
- [ ] İK personeli tüm akışı (yükleme → onay) arayüzden, API'ye elle istek atmadan tamamlayabiliyor

---

## FAZ 8 — Multi-Tenant Sıkılaştırma + Cila

**Yapılacaklar:**
- İkinci bir demo şirket eklenir, `company_id` izolasyonu gerçekten test edilir
- PostgreSQL Row Level Security (RLS) eklenir
- Hata yönetimi, loglama, README

### Faz 8 — Definition of Done
- [ ] B şirketinin kullanıcısı, A şirketinin verisine hiçbir şekilde erişemiyor (RLS testi dahil)

---

## Kod Asistanları İçin Genel Kurallar

1. **Faz sırasını atlama.** Her faz bir öncekinin üzerine kurulu; örneğin Faz 5 (Celery) olmadan Faz 6'ya (email) geçilmez.
2. **Bölüm 0'daki teknoloji kararlarını sorgulama/değiştirme** — bu kararlar önceden tartışılıp gerekçelendirilmiştir.
3. Her faz sonunda ilgili **Definition of Done** listesi işaretlenmeden bir sonraki faza geçilmemelidir.
4. Proje kodu her zaman WSL2/Ubuntu dosya sisteminde (`~/projects/ik-asistan`), Windows tarafında (`/mnt/c/...`) değil.
5. Ollama çağrıları `OLLAMA_BASE_URL` ortam değişkeni üzerinden yapılmalı, adres kod içine sabit yazılmamalı.

## Geliştirme Ortamı Süreç Yönetimi (Honcho + tmux)

Faz 5-6 arası, çoklu terminal yönetimi (uvicorn, celery worker, celery beat, Ollama, WSL2 kabuğu) pratik bir sorun haline geldiği için, geliştirme akışı **Honcho + tmux** ile sadeleştirilmiştir.

**Bileşenler:**
- `backend/Procfile.dev` — `web` (uvicorn), `worker` (celery worker), `beat` (celery beat) süreçlerini tek dosyada tanımlar.
- `run_dev.sh` (proje kökünde) — Docker'ı ayağa kaldırır, `ik-dev` adlı bir tmux oturumunda Honcho'yu arka planda başlatır, 10 saniye bekler, `check_connections.py` ile sağlık kontrolü yapar, başarılıysa log ekranına (`tmux attach`) bağlanır.
- `backend/scripts/check_connections.py` — Faz 0'daki health-check scriptinin genişletilmiş hali; artık PostgreSQL/Redis/Ollama'nın yanında **FastAPI (`/health`), Celery Worker (ping) ve Celery Beat (süreç kontrolü)** de dahil, 6 servisi tek seferde doğruluyor.
- `.gitignore`'a `celerybeat-schedule*` eklendi (Celery Beat'in ürettiği yerel zamanlama dosyası).

**Standart rutin:**
```bash
bash run_dev.sh          # her şeyi başlatır, health-check yapar, log ekranına bağlanır
# Ctrl+B, sonra D          → oturumdan ayrıl (servisler arka planda çalışmaya devam eder)
tmux attach -t ik-dev     # log ekranına geri dön
# Oturum içindeyken Ctrl+C → Honcho'yu durdurur; gerekirse ayrıca `docker compose down`
```

**Bilinen sınırlamalar / ileri iyileştirme notları:**
- ~~Sabit `sleep 10`, garanti bir bekleme değil~~ — düşük öncelikli, henüz ele alınmadı.
- ~~`check_celery_beat`, gerçek zamanlama işlevselliğini değil, sadece sürecin var olduğunu (`pgrep`) doğruluyor~~ — bilinen, kabul edilen bir sınırlama.
- **Çözüldü:** `stop_dev.sh` artık kapatmadan önce `backend/scripts/check_active_tasks.py` ile aktif Celery görevi olup olmadığını kontrol ediyor, varsa kullanıcıya onay soruyor (yarıda kalmış bir OCR/RAG görevinin sessizce kaybolmasını önlemek için) — ve kapatma sonrasında Docker/port/tmux durumunu doğruluyor.
- `honcho` (Python paketi) ve `tmux` (sistem paketi), henüz bir `requirements.txt`/README'de belgelenmiş bağımlılık değil — bu dosyalar oluşturulduğunda eklenmeli.

---

## Git Commit Alışkanlığı

Proje boyunca her **anlamlı bütünlük oluşturan alt adımda** (örn. bir modelin tamamlanması, bir script'in çalışır hale gelmesi) commit atılır — her küçük dosya değişikliğinde değil.

**Mesaj formatı:** `"Faz X.Y: [ne yapıldı, kısa]"` — örnek: `"Faz 2.2: Company modeli oluşturuldu (multi-tenancy temeli)"`.

**Standart akış:**
```bash
git status              # .env ve .venv/ görünmemeli, .gitignore'da tanımlı
git add .
git commit -m "Faz X.Y: ..."
```

Şu ana kadar atılan commit'ler: Faz 0-1 (ortam kurulumu + AI model testleri), Faz 2.1 (SQLAlchemy/Alembic kurulumu), Faz 2.2 (Company modeli), Faz 2.3 (Document/DocumentChunk modelleri), Faz 2.4 (EmailThread/Message modelleri), Faz 2.5 (ilk migration oluşturuldu ve uygulandı).

## Şu Anki Durum / Devam Noktası

**Tamamlanan:** Faz 0, Faz 1, Faz 2 (tüm alt adımlarıyla).
**Sırada:** Faz 3 — FastAPI + Senkron Ingestion Akışı (`POST /documents/upload`, `POST /documents/{id}/approve` endpoint'leri).

**Tamamlanan:** Faz 0, Faz 1, Faz 2, Faz 3, Faz 4, Faz 5, Faz 6 (tamamı) + geliştirme ortamı süreç yönetimi (Honcho/tmux, aktif görev kontrolü) + Faz 7.1-7.5 (Next.js iskeleti, Tailwind+shadcn, CORS, OCR onay ekranı [görsel+metin düzenleme dahil], `/test` senaryo simülasyon paneli — `test_emails.json` ile 22 senaryo).
**Sırada:** Faz 7.6 — Belge Yönetimi (genel görünüm, tüm durumlar).

Yeni bir sohbette kaldığımız yerden devam edilecekse: bu dosya (`Gelistirme_Plani.md`) ve `Proje_Dokumantasyonu.md` yeterlidir — ikisi birlikte projenin tüm mimari gerekçelerini, alınan kararları ve şu ana kadarki ilerlemeyi kapsar.