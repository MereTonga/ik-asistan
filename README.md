# İK E-Posta Asistanı

Şirket içi İK dokümanlarını yapay zeka ile dijitalleştirip, çalışanların e-posta ile sorduğu soruları **otomatik ama güvenilir** şekilde yanıtlayan bir sistem. Tüm yapay zeka işlemleri **lokal** çalışır (Ollama) — belge içerikleri ve e-postalar hiçbir bulut AI servisine gönderilmez.

> **Not:** Bu, bir **portföy/öğrenme projesidir.** Çekirdek işlevsellik gerçek e-posta hesaplarıyla uçtan uca test edilmiş ve çalışır durumdadır, ancak ticari kullanıma hazır değildir (bkz. [Bilinen Sınırlamalar](#bilinen-sınırlamalar)).

---

## İçindekiler

- [Ne İşe Yarar?](#ne-i̇şe-yarar)
- [Nasıl Çalışır?](#nasıl-çalışır)
- [Teknoloji Yığını](#teknoloji-yığını)
- [Ön Gereksinimler](#ön-gereksinimler)
- [Kurulum](#kurulum)
- [Çalıştırma](#çalıştırma)
- [Kullanım](#kullanım)
- [Proje Yapısı](#proje-yapısı)
- [Test](#test)
- [Bilinen Sınırlamalar](#bilinen-sınırlamalar)
- [Diğer Dokümanlar](#diğer-dokümanlar)

---

## Ne İşe Yarar?

Bir şirkette çalışanlar sürekli aynı soruları sorar:

> *"Yıllık izin hakkım ne zaman başlıyor?"*
> *"Mesai ücreti nasıl hesaplanıyor?"*
> *"Uzaktan çalışmada haftada kaç gün ofise gelmem gerekiyor?"*

Bu soruların cevapları genelde bir yerde **yazılıdır** — ama kağıt üzerinde, taranmış bir PDF'te ya da sadece İK çalışanının hafızasında. Sonuç: İK departmanı zamanının önemli bir kısmını aynı soruları tekrar tekrar cevaplayarak geçirir.

**Bu sistem ne yapar:**

1. İK yöneticisi, kural belgesinin fotoğrafını/PDF'ini yükler → yapay zeka bunu düzenli metne çevirir.
2. **Bir insan kontrol eder ve onaylar** (metni düzeltebilir de) — yapay zeka çıktısı asla otomatik yayına alınmaz.
3. Çalışan `ik@sirket.com` adresine soru gönderir → sistem maili otomatik yakalar.
4. Onaylanmış belgelerde net bir cevap varsa kibar bir e-posta yanıtı gönderir; **cevap yoksa uydurmaz**, soruyu gerçek bir İK çalışanına yönlendirir.

---

## Nasıl Çalışır?

### Belge Yükleme Akışı

```
İK yöneticisi belge yükler
         │
         ▼
   Dosya türü nedir?
         │
         ├─ Metin katmanlı PDF ──► pdfplumber (AI yok, %100 doğru)
         ├─ Temiz taranmış görsel ──► glm-ocr (hafif OCR modeli)
         └─ Karmaşık fotoğraf ──► qwen3-vl:8b (güçlü görsel model)
         │
         ▼
   İnsan onay ekranı (görsel + çıkarılan metin yan yana, metin düzenlenebilir)
         │
         ▼
   Onaylandı → metin parçalara (chunk) bölünür → her parça vektöre çevrilir → veritabanına kaydedilir
```

### Soru-Cevap Akışı

```
Çalışan e-posta gönderir
         │
         ▼
Celery Beat, her N dakikada bir IMAP ile gelen kutusunu kontrol eder
         │
         ▼
Bu mail daha önce işlendi mi? (Message-ID kontrolü) ──► Evet ise atla
         │
         ▼
Gönderen hangi şirkete ait? (e-posta domain'inden)
         │
         ▼
Soru vektöre çevrilir → o şirkete ait onaylı belgelerde en yakın parçalar aranır
         │
         ├─ Benzerlik eşiğin altında ──► "Bilgi yok, İK'ya ilettim" (LLM hiç çağrılmaz)
         │
         └─ Eşiğin üstünde ──► LLM cevap üretir
                                    │
                                    ▼
                          Groundedness kontrolü: "Bu cevap gerçekten kaynakta var mı?"
                                    │
                                    ├─ HAYIR ──► "Bilgi yok, İK'ya ilettim"
                                    └─ EVET ──► Cevap e-posta ile gönderilir
```

### Mimari Bileşenler

| Bileşen | Görevi |
|---|---|
| **FastAPI** (`api`) | HTTP API — belge yükleme, onaylama, listeleme, analitik |
| **Celery Worker** | Ağır işleri arka planda yapar (OCR, embedding, RAG, e-posta) |
| **Celery Beat** | Periyodik görevleri tetikler (gelen kutusu kontrolü) |
| **PostgreSQL + pgvector** | İlişkisel veri **ve** vektör arama, tek veritabanında |
| **Redis** | Celery'nin görev kuyruğu + sonuç deposu |
| **Next.js** (`frontend`) | Yönetim paneli (onay ekranı, test paneli, analitik) |
| **Ollama** (host'ta) | Tüm yapay zeka modelleri (LLM, OCR, görsel, embedding) |

---

## Teknoloji Yığını

**Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Celery, LangGraph, pytest
**Veritabanı:** PostgreSQL 16 + pgvector
**Kuyruk / Önbellek:** Redis 7
**Frontend:** Next.js (App Router, TypeScript), Tailwind CSS, shadcn/ui
**Yapay Zeka (Ollama üzerinden, lokal):**
- `qwen3.5:9b` — metin üretimi (cevap yazma, groundedness kontrolü)
- `qwen3-vl:8b` — karmaşık görsellerden OCR
- `glm-ocr` — temiz belgelerden hızlı OCR
- `qwen3-embedding:0.6b` — metin vektörleştirme (1024 boyut)

**Altyapı:** Docker + Docker Compose, GitHub Actions (CI)

---

## Ön Gereksinimler

### Donanım

- **NVIDIA GPU, en az 8 GB VRAM** (bu projede RTX 5060 Ti 8GB ile geliştirildi ve test edildi).
- Yeterli disk alanı (~20 GB — modeller + Docker imajları).

> GPU olmadan da çalışır ama modeller CPU'da çok yavaş olur (dakikalar sürebilir).

### Yazılım

| Gereksinim | Not |
|---|---|
| **Docker + Docker Compose** | Uygulamanın tamamı container'da çalışır |
| **Ollama** | **Host makinede** kurulu olmalı (container içinde değil) — GPU erişimi için |
| **Bir Gmail hesabı + App Password** | E-posta entegrasyonu için (2 adımlı doğrulama açık olmalı) |

> **Neden Ollama container'da değil?** Modellerin GPU'ya doğrudan erişmesi gerekiyor. Windows + WSL2 ortamında GPU sürücü erişimi, Ollama'nın host'ta (Windows tarafında) native çalışmasıyla çok daha sorunsuz.

### Ollama Modellerini İndirme

```bash
ollama pull qwen3.5:9b
ollama pull qwen3-vl:8b
ollama pull glm-ocr
ollama pull qwen3-embedding:0.6b
```

### Ollama'yı Dışarıya Açma (Önemli)

Ollama varsayılan olarak sadece `127.0.0.1`'i dinler — container'lardan erişilebilmesi için tüm arayüzleri dinlemesi gerekir:

- **Windows:** Kullanıcı ortam değişkenlerine `OLLAMA_HOST=0.0.0.0` ekleyin, Ollama'yı tamamen kapatıp yeniden başlatın.
- **Linux/macOS:** `OLLAMA_HOST=0.0.0.0 ollama serve`

Doğrulama: `netstat -ano | findstr 11434` (Windows) çıktısında `0.0.0.0:11434` görünmeli.

> ⚠️ **Güvenlik notu:** Bu ayar, Ollama'yı yerel ağınızdaki diğer cihazlara da açar (internete değil). Halka açık bir ağdayken (kafe, havaalanı) Ollama'yı kapatın veya bu ayarı geri alın.

---

## Kurulum

### 1. Depoyu klonlayın

```bash
git clone <repo-url>
cd ik-asistan
```

### 2. `.env` dosyasını oluşturun

Proje kökünde `.env` adında bir dosya oluşturun:

```env
# --- Veritabanı ---
DATABASE_URL=postgresql://ik_asistan:dev_password_degistir@localhost:5432/ik_asistan_db
TEST_DATABASE_URL=postgresql://ik_asistan:dev_password_degistir@localhost:5432/ik_asistan_test_db

# --- Redis ---
REDIS_URL=redis://localhost:6379/0

# --- Ollama ---
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_MODEL=qwen3.5:9b
VL_MODEL=qwen3-vl:8b
OCR_MODEL=glm-ocr
EMBEDDING_MODEL=qwen3-embedding:0.6b
CONTEXT_SIZE=4096

# --- RAG Ayarları ---
RAG_CONFIDENCE_THRESHOLD=0.55
RAG_TOP_K=3
GROUNDEDNESS_CHECK_ENABLED=true

# --- E-posta (IMAP/SMTP) ---
EMAIL_ADDRESS=sizin-hesabiniz@gmail.com
EMAIL_APP_PASSWORD=gmail-app-password-buraya
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_DRY_RUN=true
EMAIL_POLL_INTERVAL_SECONDS=300

# --- Loglama ---
LOG_LEVEL=INFO
```

> **`EMAIL_DRY_RUN=true` ile başlayın.** Bu modda sistem gelen kutusunu okur, cevap üretir, ama **gerçek mail göndermez** — sadece konsola yazdırır. Her şeyin doğru çalıştığından emin olduktan sonra `false` yapın.

> **Gmail App Password nasıl alınır:** Google Hesabı → Güvenlik → 2 Adımlı Doğrulama (açık olmalı) → Uygulama Şifreleri → yeni bir şifre oluşturun. Normal hesap şifreniz **çalışmaz.**

### 3. Sistemi başlatın

```bash
docker compose up -d --build
```

İlk çalıştırmada imajların inşası birkaç dakika sürer. Bu komut şunları yapar:
1. PostgreSQL ve Redis'i başlatır (hazır olmalarını bekler)
2. `pgvector` eklentisini otomatik etkinleştirir
3. Veritabanı şemasını oluşturur (`alembic upgrade head`)
4. API, Worker, Beat ve Frontend'i başlatır

### 4. Doğrulayın

```bash
docker compose ps           # tüm servisler "Up" olmalı
curl http://localhost:8000/health   # {"status":"healthy"} dönmeli
```

Tarayıcıda `http://localhost:3000` adresine gidin — yönetim paneli açılmalı.

---

## Çalıştırma

```bash
docker compose up -d        # başlat (arka planda)
docker compose logs -f      # tüm logları canlı izle
docker compose logs -f worker   # sadece worker loglarını izle
docker compose down         # durdur
docker compose down -v      # durdur + VERİTABANINI SİL (dikkatli kullanın!)
```

**Erişim adresleri:**
- Yönetim paneli: http://localhost:3000
- API dokümantasyonu (Swagger): http://localhost:8000/docs

---

## Kullanım

### İlk Kurulum: Bir Şirket Oluşturun

Sistem çok kiracılı (multi-tenant) çalışır — her belge ve e-posta bir şirkete aittir. İlk şirketi elle oluşturmanız gerekir:

```bash
docker compose exec postgres psql -U ik_asistan -d ik_asistan_db -c \
  "INSERT INTO companies (id, name, email_domain, created_at) \
   VALUES (gen_random_uuid(), 'Örnek Şirket', 'ornek-sirket.com', now()) RETURNING id;"
```

Dönen UUID'yi not edin — frontend'de `company_id` olarak kullanılıyor (şu an sabit kodlu, bkz. Bilinen Sınırlamalar).

> `email_domain`, gelen e-postanın hangi şirkete ait olduğunu belirler. Örneğin `ahmet@ornek-sirket.com` adresinden gelen bir mail, bu şirkete eşleşir.

### Belge Yükleme ve Onaylama

1. `http://localhost:3000/documents` → **"+ Yeni Belge Yükle"**
2. Dosyayı seçin (`.jpg`, `.png`, `.pdf`)
3. Görsel yüklüyorsanız kaliteyi seçin:
   - **Temiz** — düz taranmış, iyi ışıklı belge (hızlı OCR)
   - **Karmaşık** — telefonla çekilmiş, eğik/gölgeli fotoğraf (güçlü ama yavaş OCR)
4. Yükleme arka planda işlenir (karmaşık fotoğraflarda birkaç dakika sürebilir)
5. Listeden belgeye tıklayın → **solda orijinal görsel, sağda çıkarılan metin**
6. Metinde hata varsa **düzeltin ve "Kaydet"** deyin
7. Doğru olduğundan emin olduğunuzda **"Onayla"** → metin parçalanır, vektörleştirilir ve aranabilir hale gelir

> ⚠️ **Onay adımını ciddiye alın.** OCR bazen sessizce yanlış okur — özellikle sayılar, e-posta adresleri, tarihler. Onaylanan metin, çalışanlara verilecek cevapların kaynağı olur.

### Test Paneli (Gerçek Mail Göndermeden Deneme)

`http://localhost:3000/test` — hazır senaryolarla sistemi test edebilirsiniz. Her senaryo, gerçek bir e-posta gelmiş gibi işlenir (IMAP adımı atlanır), sonucu anında görürsünüz. Senaryolar `backend/app/email_service/test_data/test_emails.json` dosyasında — istediğiniz gibi düzenleyebilirsiniz.

### Analitik

`http://localhost:3000/analytics` — toplam soru sayısı, kaç tanesinin İK'ya yönlendirildiği, ve **en çok yönlendirilen konular.** Bu son liste değerlidir: dokümantasyonunuzda hangi konuların eksik olduğunu gösterir.

### Gerçek E-posta Akışı

`EMAIL_DRY_RUN=false` yaptıktan sonra sistem, `EMAIL_POLL_INTERVAL_SECONDS` aralığıyla gelen kutusunu kontrol eder ve otomatik cevap verir.

---

## Proje Yapısı

```
ik-asistan/
├── docker-compose.yml          # Tüm servislerin tanımı
├── .env                        # Yapılandırma (Git'e dahil değil)
├── db/init/                    # Veritabanı ilk kurulum betikleri (pgvector)
├── .github/workflows/          # GitHub Actions CI
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                # Veritabanı migration'ları
│   ├── app/
│   │   ├── main.py             # FastAPI uygulaması
│   │   ├── config.py           # .env doğrulama (pydantic-settings)
│   │   ├── celery_app.py       # Celery yapılandırması + Beat zamanlaması
│   │   ├── logging_config.py   # Merkezi loglama
│   │   ├── models/             # Veritabanı modelleri (SQLAlchemy)
│   │   ├── api/                # HTTP endpoint'leri
│   │   ├── services/           # Belge işleme (OCR, chunk, embedding)
│   │   ├── rag/                # Vektör arama + LangGraph karar akışı
│   │   ├── email_service/      # IMAP okuma, SMTP gönderme, thread eşleştirme
│   │   └── tasks/              # Celery görevleri
│   ├── scripts/                # Yardımcı/tanı betikleri
│   └── tests/                  # pytest testleri
│
└── frontend/
    ├── Dockerfile              # Multi-stage build
    ├── app/                    # Next.js sayfaları (App Router)
    │   ├── documents/          # Belge listesi, detay/onay, yükleme
    │   ├── test/               # Senaryo simülasyon paneli
    │   └── analytics/          # Analitik panosu
    └── components/             # Paylaşılan bileşenler (navbar, shadcn/ui)
```

---

## Test

Testler ayrı bir veritabanı kullanır ve her test kendi transaction'ında çalışıp geri alınır — gerçek verinize dokunmaz. Ollama'ya hiç bağlanmazlar (mock'lanmıştır), bu yüzden hızlıdırlar (~2 saniye).

```bash
cd backend
pytest tests/ -v                                  # tüm testler
pytest tests/ --cov=app --cov-report=term-missing # coverage raporu ile
```

> Testleri **yerel olarak** çalıştırmak için bir Python sanal ortamı ve `TEST_DATABASE_URL`'in işaret ettiği veritabanının kurulu olması gerekir. Her push'ta GitHub Actions bunu otomatik olarak temiz bir ortamda çalıştırır.

---

## Bilinen Sınırlamalar

Bu proje bilinçli olarak sınırlı bir kapsamda tutulmuştur. En önemlileri:

**Güvenlik**
- **Kimlik doğrulama yok.** Hiçbir endpoint "bu isteği kim atıyor" diye sormuyor; frontend'de `company_id` sabit kodlu. Gerçek bir çok-kullanıcılı ürün için ilk eklenmesi gereken şey budur.
- **Row Level Security (RLS) yok.** Şirket izolasyonu sadece uygulama kodunda (`WHERE company_id = ...`) — testlerle doğrulanmış durumda, ancak veritabanı seviyesinde ikinci bir savunma hattı yok.
- `GET /documents` ve `GET /documents/{id}` endpoint'leri `company_id` filtrelemiyor.
- Yüklenen dosyalar `/uploads` altında herkese açık servis ediliyor (yetkilendirme yok).

**E-posta**
- Domain eşleştirmesi **"bir domain = bir şirket"** varsayımına dayanıyor. Kişisel mail adresi kullanan çalışanlar/stajyerler sistemle iletişim kuramaz.
- Paylaşılan domain (`gmail.com` gibi) bir şirkete atanırsa, o domain'deki herkes o şirketin çalışanı sayılır — **veri sızıntısı riski.**
- Sistem, gelen mailin **niyetini** sınıflandırmaz — her maili bir İK sorusu varsayar (iş başvurusu, spam vb. ayırt edilmez).
- Alıntı temizleme (yanıtlardaki eski mail bloklarını ayıklama) regex tabanlı, %100 kapsayıcı değil.
- Sadece Gmail + App Password test edildi; OAuth2 ve Outlook/Exchange kurumsal IMAP denenmedi.

**RAG Kalitesi**
- Chunk'lama basit (paragraf bölme) — semantik/başlık hiyerarşisine duyarlı değil.
- Güven eşiği (0.55) küçük bir örneklemden tahmin edildi, gerçek ölçekte kalibre edilmedi.
- Gerçek bir reranker modeli yok (groundedness check, aynı LLM ile ikinci bir doğrulama olarak eklendi).

**Diğer**
- Frontend için hiç otomatik test yok.
- KVKK / veri saklama-silme politikası uygulanmadı.
- Test verisi (şirketler, belgeler) elle oluşturuluyor — tekrarlanabilir bir seed betiği yok.
- `run_dev.sh` / `stop_dev.sh` (Honcho + tmux geliştirme ortamı) artık Docker Compose ile çakışıyor; proje Docker moduna geçtiği için güncellenmedi.

---

## Diğer Dokümanlar

| Dosya | İçerik |
|---|---|
| **`Proje_Dokumantasyonu.md`** | Mimari gerekçeler — hangi teknoloji neden seçildi, sistem nasıl tasarlandı |
| **`Gelistirme_Plani.md`** | Uygulama geçmişi — faz faz ne yapıldı, hangi sorunlar çıktı ve nasıl çözüldü, hangi kararlar neden alındı |

Projeyi yeni inceleyen biri için önerilen okuma sırası: **bu README → `Proje_Dokumantasyonu.md` → `Gelistirme_Plani.md`**