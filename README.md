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
   (işleme hatası → "Hatalı" durumu + hata mesajı → "Yeniden işle")
```

### Soru-Cevap Akışı

```
Çalışan e-posta gönderir
         │
         ▼
Celery Beat, her N dakikada bir IMAP ile gelen kutusunu kontrol eder (okunmamışlar, önce yalnızca başlıklar)
         │
         ▼
Elenir mi? daha önce işlenmiş (Message-ID) · oto-yanıt / bounce / liste maili · bilinmeyen domain · hız sınırı
         │   (elenenler okunmamış kalır; bilinmeyen domain ve oto-yanıt 30 gün hatırlanır, tekrar indirilmez)
         ▼
Gönderen hangi şirkete ait? (e-posta domain'inden) → mailin tamamı indirilir, thread'e bağlanır
         │   (takip sorusuysa aynı yazışmanın son 4 mesajı LLM'e bağlam olarak verilir; arama
         │    "önceki soru + güncel soru" ile de yapılır)
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
         │
         ▼
Gelen kutusunda mail "okundu" işaretlenir; İK'ya yönlendirilenler ayrıca YILDIZLANIR (İK bir bakışta görsün)
```

Gönderilen cevaplar `Auto-Submitted: auto-replied` gibi standart otomatik yanıt başlıkları taşır; karşı taraftaki tatil mesajı sistemleri bize tekrar yazmaz. Aynı gönderene saatte en fazla `EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR` (varsayılan 5) cevap gider.

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
REDIS_URL=redis://:redis-parolasi-buraya@localhost:6379/0

# --- Compose parolaları (docker-compose.yml bunları ${...} ile okur) ---
# POSTGRES_PASSWORD, DATABASE_URL/TEST_DATABASE_URL içindeki parolayla aynı olmalı.
# REDIS_PASSWORD, REDIS_URL içindeki parolayla aynı olmalı.
POSTGRES_PASSWORD=dev_password_degistir
REDIS_PASSWORD=redis-parolasi-buraya

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

İsteğe bağlı ayarlar (varsayılanları `backend/app/config.py` içinde): `HR_NOTIFY_EMAIL` (boş), `DEFAULT_COMPANY_DOMAIN` (boş; dışarıdan gelen mailleri karşılayan şirket), `MAX_UPLOAD_MB` (20), `EMAIL_MAX_REPLIES_PER_SENDER_PER_HOUR` (5), `EMAIL_SKIP_MEMORY_DAYS` (30), `THREAD_MATCH_WINDOW_DAYS` (30), `THREAD_MEMORY_MESSAGES` (4; takip sorularında LLM'e verilen önceki mesaj sayısı, 0 kapatır), `THREAD_MEMORY_MAX_CHARS` (500), `THREAD_RESOLVE_AFTER_DAYS` (14), `THREAD_RETENTION_DAYS` (0 = kapalı; >0 ise bu kadar günden eski yazışmalar her gece silinir), `TASK_SOFT_TIME_LIMIT_SECONDS` (1800), `NEXT_PUBLIC_API_URL` (frontend build-arg, `http://localhost:8000`), `TZ` (container'ların log/zamanlama saat dilimi, `Europe/Istanbul`; veritabanı her zaman UTC saklar, panel tarayıcının saat dilimini gösterir).

> **Ağ notu:** Compose, tüm portları (`5432`, `6379`, `8000`, `3000`) yalnızca `127.0.0.1`'e bağlar; servisler aynı makineden `localhost` ile erişilir, yerel ağdaki diğer cihazlara açılmaz. Redis parola ister, Postgres parolası ve Redis parolası `.env`'den gelir. **Mevcut bir `pgdata` volume'unda `POSTGRES_PASSWORD` değerini değiştirmek parolayı değiştirmez** (parola ilk kurulumda belirlenir); değiştirmek için `ALTER USER ik_asistan PASSWORD '...'` çalıştırın ya da `docker compose down -v` ile sıfırdan kurun.

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

Aynı işi API ile de yapabilirsiniz: `POST /companies/add` (form alanları `name`, `email_domain`, isteğe bağlı `hr_notify_email`). Panel, kayıtlı şirketleri sağ üstteki **şirket seçici**den okur; seçim tarayıcıda hatırlanır ve yükleme, test paneli, analitik bu seçime göre çalışır.

**İK bildirimi (isteğe bağlı):** Bot ve İK aynı gelen kutusunu kullanıyorsa yönlendirilen sorular o kutuda yıldızlı görünür, ek bir şey gerekmez. İK'nın **ayrı** bir adresi varsa şirkete `hr_notify_email` verin; her yönlendirmede çalışanın sorusu bu adrese iletilir ve maildeki `Reply-To` çalışanın adresi olur, İK "Yanıtla" ile doğrudan çalışana yazar. Tüm şirketler için ortak bir adres `.env`'de `HR_NOTIFY_EMAIL` ile verilebilir. Güncellemek için:

```bash
curl -X PATCH http://localhost:8000/companies/<id> -H 'Content-Type: application/json' -d '{"hr_notify_email": "ik.muduru@sirket.com"}'
```

### Kime Ne Cevap Verilir?

Belgelerin iki görünürlüğü vardır: **Şirket içi** (varsayılan) ve **Herkese açık**. Gönderen adresine göre kapsam belirlenir:

| Gönderen | Nasıl tanınır | Kullanılan belgeler |
|---|---|---|
| Şirket çalışanı | Adresin domain'i şirketin `email_domain`'i | Şirket içi + herkese açık |
| Kişisel adres kullanan çalışan/stajyer | Şirketin **yetkili gönderen** listesinde | Şirket içi + herkese açık |
| Dışarıdan biri (aday, eski çalışan...) | Hiçbiri; `.env`'de `DEFAULT_COMPANY_DOMAIN` ayarlıysa o şirkete yönlenir | Yalnızca herkese açık |

`DEFAULT_COMPANY_DOMAIN` boşsa dışarıdan gelen mailler atlanır ve okunmamış kalır (eski davranış). Dışarıdan gelenlere LLM "soran kişi çalışan değil" notuyla cevap üretir; bu yazışmalar analitikte ayrı sayılır.

```bash
# Kişisel adres kullanan bir çalışanı şirkete bağla / listele / sil
curl -X POST http://localhost:8000/companies/<id>/senders -H 'Content-Type: application/json' -d '{"email": "ali@gmail.com", "note": "stajyer"}'
curl http://localhost:8000/companies/<id>/senders
curl -X DELETE http://localhost:8000/companies/<id>/senders/<sender_id>

# Şirketi sil (belgesi/yazışması varsa force gerekir; hepsi birlikte silinir)
curl -X DELETE "http://localhost:8000/companies/<id>?force=true"
```

Şirket ya da yetkili gönderen eklendiğinde, daha önce "bilinmeyen domain" diye atlanan mailler bir sonraki turda yeniden değerlendirilir. Test panelindeki **"Dışarıdan gelen gibi çalıştır"** kutusu, gerçek mail atmadan dış gönderen davranışını dener.

> `email_domain`, gelen e-postanın hangi şirkete ait olduğunu belirler. Örneğin `ahmet@ornek-sirket.com` adresinden gelen bir mail, bu şirkete eşleşir.

### Örnek Veri (Seed)

Boş bir kurulumda sistemi hemen denemek için iki örnek şirket (`ornek-a.com`, `ornek-b.com`) ve farklı sayılarla yazılmış iki politika belgesi hazır:

```bash
docker compose exec api python -m app.seed
```

Komut `backend/seed/*.md` dosyalarını belge olarak yükler, chunk'lar ve embedding'leriyle onaylar (Ollama açık olmalı). Var olan şirket ve belgeleri atlar; tekrar çalıştırmak güvenlidir. Normal kullanımda gerekmez, belgeler panelden yüklenir.

### Belge Yükleme ve Onaylama

1. `http://localhost:3000/documents` → **"+ Yeni Belge Yükle"**
2. Dosyayı seçin (`.jpg`, `.png`, `.pdf`)
3. Görünürlüğü seçin: **Şirket içi** (yalnızca çalışanlara kaynak) ya da **Herkese açık** (dışarıdan yazanlara da). Sonradan belge detayından değiştirilebilir.
4. Görsel yüklüyorsanız kaliteyi seçin:
   - **Temiz** — düz taranmış, iyi ışıklı belge (hızlı OCR)
   - **Karmaşık** — telefonla çekilmiş, eğik/gölgeli fotoğraf (güçlü ama yavaş OCR)
4. Yükleme arka planda işlenir (karmaşık fotoğraflarda birkaç dakika sürebilir). Belge bu sırada **İşleniyor** durumundadır; detay sayfası kendini birkaç saniyede bir yeniler.
5. Listeden belgeye tıklayın → **solda orijinal görsel, sağda çıkarılan metin**
6. Metinde hata varsa **düzeltin ve "Kaydet"** deyin
7. Doğru olduğundan emin olduğunuzda **"Onayla"** → belge **İndeksleniyor** durumuna geçer, metin parçalanır, vektörleştirilir ve **Onaylı** olur
8. İşleme başarısız olursa belge **Hatalı** durumuna düşer ve hata mesajı görünür; **"Yeniden işle"** ile tekrar denenir. Yazısız ya da çok bozuk bir görselde OCR modeli saçmalayabilir (yönergeyi tekrar etmek, Çince karakterler, aşırı tekrar); sistem bunu tanır ve belgeyi onaya sunmak yerine Hatalı yapar. Onaylı bir belgeyi güncel parçalama yöntemiyle yeniden indekslemek için **"Yeniden parçala"** kullanılır.
9. Onaylı bir belgeyi aramadan çıkarmak için **"Emekliye ayır"** (metin saklanır, **"Yeniden etkinleştir"** ile geri gelir); belgeyi parçaları ve dosyasıyla birlikte kalıcı olarak kaldırmak için **"Sil"** (iki adımlı onay). İşleme sürerken silinemez.

Yükleme sınırları: yalnızca `.pdf`, `.jpg`, `.jpeg`, `.png`; dosya içeriği uzantısıyla uyuşmalı; üst boyut `MAX_UPLOAD_MB` (varsayılan 20 MB).

> ⚠️ **Onay adımını ciddiye alın.** OCR bazen sessizce yanlış okur — özellikle sayılar, e-posta adresleri, tarihler. Onaylanan metin, çalışanlara verilecek cevapların kaynağı olur.

### Test Paneli (Gerçek Mail Göndermeden Deneme)

`http://localhost:3000/test` — hazır senaryolarla sistemi test edebilirsiniz. Her senaryo, gerçek bir e-posta gelmiş gibi işlenir (IMAP adımı atlanır), sonucu anında görürsünüz. Simülasyon, `EMAIL_DRY_RUN` ayarından bağımsız olarak **hiçbir zaman gerçek e-posta göndermez**; yalnızca cevabı üretir ve kaydeder. Bir senaryo çalıştıktan sonra altındaki **"Takip sorusu"** kutusu aynı yazışmaya bağlanır; böylece konuşma hafızasını ("Peki ya cuma günleri?") gerçek mail atmadan denersiniz. Senaryolar arasında aday soruları da (staj başvurusu, çalışma belgesi) var; "Dışarıdan gelen gibi çalıştır" ile birlikte kullanın. Senaryolar `backend/app/email_service/test_data/test_emails.json` dosyasında — istediğiniz gibi düzenleyebilirsiniz.

### Analitik

`http://localhost:3000/analytics` — toplam soru sayısı, kaç tanesinin İK'ya yönlendirildiği, cevaplarda bulunan en iyi parçanın **ortalama benzerliği** (güven eşiğini kalibre etmek için), groundedness kontrolünden geçme oranı ve **en çok yönlendirilen konular.** Bu son liste değerlidir: dokümantasyonunuzda hangi konuların eksik olduğunu gösterir.

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
│   ├── scripts/                # Honcho ortamı için sağlık kontrolleri + IMAP smoke betiği
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
- **Kimlik doğrulama yok.** Hiçbir endpoint "bu isteği kim atıyor" diye sormuyor; paneldeki şirket seçici bir yetki kontrolü değil, yalnızca görünüm filtresidir. Gerçek bir çok-kullanıcılı ürün için ilk eklenmesi gereken şey budur.
- **Row Level Security (RLS) yok.** Şirket izolasyonu sadece uygulama kodunda (`WHERE company_id = ...`) — testlerle doğrulanmış durumda, ancak veritabanı seviyesinde ikinci bir savunma hattı yok.
- `GET /documents` için `company_id` filtresi isteğe bağlı; `GET /documents/{id}` ve belge işlem endpoint'leri şirket kontrolü yapmıyor (kimlik doğrulama olmadığı için anlamlı bir kontrol de mümkün değil).
- Yüklenen dosyalar `/uploads` altında herkese açık servis ediliyor (yetkilendirme yok).

**E-posta**
- Çalışan tanıma domain ve yetkili gönderen listesine dayanır; `From` başlığı doğrulanmadığı için sahte `From` ile çalışan gibi görünmek mümkündür (cevap sahte adrese gider).
- Paylaşılan domain (`gmail.com` gibi) bir şirkete atanırsa, o domain'deki herkes o şirketin çalışanı sayılır — **veri sızıntısı riski.** Kişisel adresler için şirket domain'i yerine yetkili gönderen listesini kullanın.
- `DEFAULT_COMPANY_DOMAIN` ayarlıysa İK adresine yazan herkes "herkese açık" belgelerden cevap alır; açık belgeleri seçmek İK'nın sorumluluğudur.
- Sistem, gelen mailin **niyetini** sınıflandırmaz — her maili bir İK sorusu varsayar (iş başvurusu, spam vb. ayırt edilmez). Yalnızca oto-yanıt, teslim raporu, liste ve sistem adresi mailleri başlıklarından tanınıp elenir.
- Alıntı temizleme (yanıtlardaki eski mail bloklarını ayıklama) regex tabanlı, %100 kapsayıcı değil.
- Gönderenin `From` başlığı doğrulanmaz (SPF/DKIM sonuçları okunmaz); sahte `From` ile bot tetiklenebilir, cevap sahte adrese gider.
- "İK'ya ilettim" cevabı, gelen kutusundaki yıldız işareti ve (ayarlıysa) `hr_notify_email` bildirimi anlamına gelir. Gerçek İK aynı kutudan çalışana cevap yazarsa bot bunu görmez; çalışanın sonraki takip sorusunu yine kendisi cevaplamaya çalışır.
- Sadece Gmail + App Password test edildi; OAuth2 ve Outlook/Exchange kurumsal IMAP denenmedi.

**RAG Kalitesi**
- Chunk'lama kural tabanlı (boş satır + Markdown başlığı ile blok, 1500 karakter pencere, 200 karakter örtüşme, başlık ön eki) — anlamsal (embedding tabanlı) bölme yok.
- Güven eşiği (0.55) küçük bir örneklemden tahmin edildi, gerçek ölçekte kalibre edilmedi.
- Gerçek bir reranker modeli yok (groundedness check, aynı LLM ile ikinci bir doğrulama olarak eklendi).

**Diğer**
- Frontend için hiç otomatik test yok.
- KVKK / veri saklama-silme politikası uygulanmadı.
- Test verisi (şirketler, belgeler) elle oluşturuluyor — tekrarlanabilir bir seed betiği yok.
- `run_dev.sh` / `stop_dev.sh` (Honcho + tmux geliştirme ortamı) artık Docker Compose ile çakışıyor; proje Docker moduna geçtiği için güncellenmedi.
- Ekim 2026'da yapılan kapsamlı denetimin tam bulgu listesi ve açık kararlar `Denetim_Raporu.md` dosyasındadır (Faz 11 bu listenin ilk paketidir).

---

## Diğer Dokümanlar

| Dosya | İçerik |
|---|---|
| **`Proje_Dokumantasyonu.md`** | Mimari gerekçeler — hangi teknoloji neden seçildi, sistem nasıl tasarlandı |
| **`Gelistirme_Plani.md`** | Uygulama geçmişi — faz faz ne yapıldı, hangi sorunlar çıktı ve nasıl çözüldü, hangi kararlar neden alındı |

Projeyi yeni inceleyen biri için önerilen okuma sırası: **bu README → `Proje_Dokumantasyonu.md` → `Gelistirme_Plani.md`**