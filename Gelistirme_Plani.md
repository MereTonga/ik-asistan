# Geliştirme Planı ve Uygulama Rehberi

## Yapay Zeka Destekli Dijital İK E-Posta Asistanı

> **Bu dosya kimin için?** Bu doküman, projeyi bir insan geliştiricinin veya bir kod asistanının (Claude Code, Cursor, GitHub Copilot, Antigravity vb.) sıfırdan, sırayla takip edebilmesi için yazılmıştır. Her fazda: ne yapıldığı, neden bu sırada/bu şekilde yapıldığı, yol boyunca bulunup düzeltilen gerçek sorunlar, ve bilinen sınırlamalar belirtilmiştir. Genel mimari gerekçeleri için bkz. `Proje_Dokumantasyonu.md`. Bu dosya, ondan farklı olarak **uygulama sırasına, somut kararlara ve gerçek hata/çözüm geçmişine** odaklanır — proje ilerledikçe periyodik olarak baştan düzenlenip güncel tutulur.

---

## 0. Kesinleşmiş Teknik Kararlar (Referans Tablosu)

Kod asistanları bu bölümü **değiştirmeden, sorgulamadan** referans almalı — bu kararlar tartışılıp gerekçelendirilmiş ve çoğu gerçek testlerle doğrulanmıştır.

| Katman | Karar | Not |
|---|---|---|
| LLM (metin üretimi) | `qwen3.5:9b` (Ollama) | 8GB VRAM sınırı nedeniyle 27b değil 9b. `num_ctx=4096` (`.env`: `CONTEXT_SIZE`) ile GPU kullanımı optimize edildi. |
| Görsel/OCR (karmaşık belge) | `qwen3-vl:8b` (Ollama) | `4b` test edildi ve **reddedildi** (hızlı ama anlam bozan halüsinasyonlar). CPU offload'a rağmen 8b'de kalınıyor — OCR nadir/toplu bir iş, doğruluk hızdan önemli. |
| OCR (temiz belge) | `glm-ocr` (Ollama) | 0.9B, hafif, hızlı — düz taranmış belgeler için varsayılan. |
| PDF metin çıkarma | `pdfplumber` / `PyMuPDF` | Metin katmanlı (dijital) PDF'ler için — AI kullanılmaz, %100 doğrulukla doğrulandı. |
| Embedding | `qwen3-embedding:0.6b` (Ollama) | Çıktı boyutu **1024**. Türkçe anlamsal ayrım net (aynı-anlam ~0.69, alakasız ~0.22). |
| RAG güven eşiği | `RAG_CONFIDENCE_THRESHOLD=0.55`, `RAG_TOP_K=3` (`.env`) | Faz 1'deki ölçümlerden başlangıç değeri — kesin bilimsel sonuç değil, kalibre edilebilir parametre. |
| Backend | FastAPI (Python) | Asenkron, AI kütüphaneleriyle doğal entegrasyon. |
| Kuyruk | Celery + Redis | Ağır işleri arka plana almak (broker+backend) + periyodik görevler (Celery Beat) için. |
| Veritabanı | PostgreSQL + `pgvector` | İlişkisel veri + vektör arama tek yerde. ChromaDB/MongoDB yerine tercih edildi (bkz. SSS). |
| RAG Orkestrasyonu | LangGraph | Koşullu dallanma (cevap üret / insana yönlendir) için. |
| **E-posta** | **IMAP/SMTP doğrudan bağlantı (Gmail, App Password)** | **Revize karar** — Postmark/SendGrid yerine tercih edildi: projenin "lokal AI, veri dışarı çıkmıyor" hikayesiyle tutarlılık için. Webhook yerine **Celery Beat ile periyodik polling**. |
| Frontend | Next.js (App Router, `src/` klasörü **yok**) + Tailwind + shadcn/ui (Base UI + Lumia preset) | |
| Test | pytest + ayrı PostgreSQL test veritabanı | SQLite kullanılmadı (pgvector desteklemiyor). Transactional rollback stratejisi. |
| Loglama | Python `logging` + `RotatingFileHandler` | Merkezi `get_logger()`, hem terminale hem `logs/app.log`'a yazar. |
| Config doğrulama | `pydantic-settings` | `.env` eksikse uygulama **başlangıçta** (fail-fast) net bir hata verir. |
| Geliştirme ortamı süreç yönetimi | Honcho (Procfile) + tmux | `run_dev.sh` / `stop_dev.sh` — tek komutla başlat/durdur, aktif görev kontrolü, kapatma doğrulaması. |

### Belge İşleme Karar Ağacı

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

- **"ChromaDB/MongoDB kullansak olmaz mıydı?"** Hayır — ikisi de bizim `company_id`'ye bağlı, foreign key'lerle ilişkili verimiz (Company→Document→DocumentChunk, EmailThread→Message) için uygun değil. `pgvector`, ilişkisel + vektör veriyi tek veritabanında, RLS gibi ileri güvenlik önlemlerine açık şekilde tutmamızı sağlıyor.
- **"Embedding modeli iki metni karşılaştırıp mı vektör üretiyor?"** Hayır — tek bir metni vektöre çevirir, karşılaştırma yapmaz. Karşılaştırma (`cosine_distance`), `pgvector` tarafında veya kodumuzda ayrıca hesaplanır. Veritabanının rolü: chunk vektörlerini **önceden hesaplanmış halde saklamak.**
- **"Webhook mu, polling mi daha güvenli?"** İkisi de farklı sebeplerle mükerrer işleme riski taşır — webhook'ta **gerçek paralellik** (sağlayıcı aynı anda birden fazla istek atabilir), polling'te **pencere sınırı** (bir mailin iki ardışık pollde de "yeni" görünmesi). İkisinin de çözümü aynı: `Message-ID` bazlı idempotency + (bizim seçtiğimiz polling'de ayrıca) dağıtık kilit.
- **"Django kullansaydık auth hazır gelmez miydi?"** Kısmen — Django'nun `User`/oturum altyapısı hazır gelirdi, ama "kullanıcı ↔ şirket" ilişkisini ve React tarafındaki giriş deneyimini yine biz kurardık. Framework seçimi bu işin bir kısmını kolaylaştırır, tamamını ortadan kaldırmaz.

---

## 1. Ortam Mimarisi (Windows / WSL2 Ayrımı)

| Konum | İçerik | Kurulum Türü |
|---|---|---|
| **Windows** | Ollama (tüm modellerle), `OLLAMA_HOST=0.0.0.0` ayarlı | Native |
| **WSL2 / Ubuntu** | Docker Engine, Python 3.12 (`.venv`), Node.js (nvm ile) | Native |
| **WSL2 / Ubuntu (Docker içinde)** | PostgreSQL + pgvector, Redis | Container |
| **WSL2 / Ubuntu** | Proje kod klasörü (`~/projects/ik-asistan`) | WSL2'nin kendi dosya sisteminde, Windows tarafında değil |

**Köprü:** WSL2 içindeki servisler Ollama'ya `http://host.docker.internal:11434` üzerinden ulaşır.

**Güvenlik notu:** `OLLAMA_HOST=0.0.0.0`, Ollama'yı sadece WSL2'ye değil **yerel ağdaki diğer cihazlara da** açar (internete değil). Halka açık ağda (kafe, havaalanı) Ollama kapatılmalı/ayar geri alınmalı.

### Geliştirme Ortamı Süreç Yönetimi (Honcho + tmux)

Çoklu terminal yönetimi (uvicorn, celery worker, celery beat, Ollama, WSL2 kabuğu) pratik bir sorun haline geldiği için sadeleştirildi:

- `backend/Procfile.dev` — `web` (uvicorn), `worker` (celery worker), `beat` (celery beat) tek dosyada.
- `run_dev.sh` (proje kökü) — Docker'ı kaldırır, `ik-dev` tmux oturumunda Honcho'yu başlatır, health-check yapar (`check_connections.py` — PostgreSQL/Redis/Ollama/FastAPI/Celery Worker/Celery Beat, 6 servis), başarılıysa log ekranına bağlanır.
- `stop_dev.sh` — **Kapatmadan önce** aktif Celery görevi var mı kontrol eder (`check_active_tasks.py`), varsa onay ister (yarıda kalan bir OCR/RAG görevinin kaybolmasını önlemek için); kapatma **sonrasında** Docker/port/tmux durumunu doğrular.

```bash
bash run_dev.sh          # başlat + health-check + log ekranına bağlan
# Ctrl+B, D               → oturumdan ayrıl (arka planda çalışmaya devam eder)
tmux attach -t ik-dev     # log ekranına geri dön
bash stop_dev.sh          # aktif görev kontrolü + durdur + doğrula
```

**Bilinen sınırlamalar:** Sabit `sleep` süresi garanti değil (retry döngüsü değil); `check_celery_beat` sadece süreç varlığını (`pgrep`) doğruluyor, fonksiyonel değil; `honcho`/`tmux` henüz `requirements.txt`/README'de belgelenmiş değil.

---

## 2. Proje Durumu Özeti

| Faz | Konu | Durum |
|---|---|---|
| 0 | Ortam Kurulumu | ✅ Tamamlandı |
| 1 | AI Çekirdeği Doğrulama | ✅ Tamamlandı |
| 2 | Veritabanı Şeması | ✅ Tamamlandı |
| 3 | FastAPI + Senkron Ingestion | ✅ Tamamlandı |
| 4 | RAG Karar Mantığı (LangGraph) | ✅ Tamamlandı |
| 5 | Celery + Redis (Asenkron) | ✅ Tamamlandı |
| 6 | E-posta Entegrasyonu (IMAP/SMTP) | ✅ Tamamlandı |
| 7 | Next.js Paneli + UI Cilası | ✅ Tamamlandı |
| 8 | Test + Loglama + Config Doğrulama | ✅ Tamamlandı |
| — | Groundedness Check (RAG kalite) | ✅ Tamamlandı |
| 9 | Multi-Tenant Sıkılaştırma | ⚠️ Kısmi kapsamla sonlandırıldı (ikinci şirket + izolasyon testleri yapıldı; RLS bilinçli olarak ertelendi) |
| — | `requirements.txt` + CI/CD (GitHub Actions) | ✅ Tamamlandı (ilk denemede başarılı) |
| 10 | Docker (uygulamanın kendisini container'lama) | ✅ Tamamlandı |
| — | Genel değerlendirme + README + dokümantasyon kapanışı | ✅ Tamamlandı — **proje kapatıldı** |

---

## FAZ 0 — Ortam Kurulumu

**Kurulanlar:** Ollama (4 model), Docker Compose (Postgres+pgvector, Redis), Python `.venv`, `.env`, `check_connections.py` health-check.

**Bulunup çözülen sorunlar:**
- `python3.12-venv` ayrıca kurulması gerekti (`sudo apt install python3.12-venv`).
- WSL2'den Ollama'ya erişilemiyordu (`Connection timed out`) → `OLLAMA_HOST=0.0.0.0` ile çözüldü (güvenlik notuyla birlikte).
- Docker container'ları sonsuza kadar "Starting" durumunda takılı kaldı → `wsl --shutdown` (Docker Desktop'ın gizli WSL dağıtımını da sıfırlıyor) ile çözüldü.

**Faz 0 tamamlandı.**

---

## FAZ 1 — Yapay Zeka Çekirdeğini İzole Şekilde Kanıtla

**Bulgular:**

| Bileşen | Sonuç |
|---|---|
| `glm-ocr` | Başarılı, hızlı. Küçük ı/i okuma hataları (Türkçe'ye özgü) — bazen anlam değiştirebiliyor. |
| `qwen3-vl:8b` | Başarılı ama CPU'ya taşıyor (~%68), yavaş (~6-7 dk). Kabul edildi — OCR nadir/toplu bir iş. |
| `qwen3-vl:4b` | Hızlı ama anlam bozan halüsinasyonlar (özellikle e-posta gibi kritik veride). **Reddedildi.** |
| `pdfplumber` | %100 doğru. |
| `qwen3-embedding:0.6b` | Anlamsal ayrım net. Embedding boyutu: **1024**. |
| `qwen3.5:9b` | Doğru, tutarlı, halüsinasyon yok. `num_ctx=4096` ile GPU kullanımı iyileşti. |

**Tasarım notu:** OCR hataları iki kategoride — kozmetik (kolay fark edilir) ve e-posta/tarih/tutar gibi "tam eşleşmesi gereken" veride sessiz-ama-yanlış üretim (fark edilmesi zor). Onay ekranında kritik alanların vurgulanması ileri faz notu.

**Faz 1 tamamlandı.**

---

## FAZ 2 — Veritabanı Şeması

**Modeller:** `Company` (UUID PK, unique `email_domain`), `Document`/`DocumentChunk` (FK ilişkileri, denormalize `company_id`, `source_type`, `status` bilinçli olarak `String` — Enum değil), `EmailThread`/`Message` (`root_message_id_header`, `sender_type`, `was_escalated`, `message_id_header` unique — idempotency için Faz 6.4'te eklendi).

**Tasarım kararları:**
- UUID PK'ler — ID enumeration saldırısına karşı.
- `company_id`'nin hem `Document` hem `DocumentChunk`'ta tekrarı — join'siz hızlı sorgu + gelecekteki RLS için.
- Thread eşleştirme: iki katmanlı (önce `Message-ID`, sonra `employee_email`+`subject` benzerliği + 30 günlük pencere).
- Thread `resolved` durumuna geçiş: Celery Beat ile periyodik kontrol (idari kapanış, gerçek memnuniyet ölçümü değil).
- KVKK/veri saklama politikası: MVP kapsamında **uygulanmadı**, bilinçli sınırlama.

**Bulunan sorun:** Alembic autogenerate, `pgvector.sqlalchemy.Vector` kolonları için gereken `import pgvector` satırını otomatik eklemiyor — migration'lar çalıştırılmadan önce gözden geçirilmeli.

**Faz 2 tamamlandı.**

---

## FAZ 3 — FastAPI + Senkron Ingestion Akışı

**Kurulanlar:** `main.py`, `document_processor.py` (karar ağacı), `POST /documents/upload`, `POST /documents/{id}/approve` (chunk'lama: `\n\n` ile paragraf bölme + `min_length=20` filtresi).

**Bulunup çözülen sorunlar:**
- `python-multipart` eksikti (FastAPI'nin `UploadFile` için gizli bağımlılığı).
- `Company` modeli hiçbir yerde import edilmediği için SQLAlchemy foreign key'i tanıyamadı (`NoReferencedTableError`) → `app/models/__init__.py`'de tüm modeller merkezi olarak import edilerek çözüldü — kalıcı bir güvenlik önlemi.

**Güvenlik notu:** Chunk'lar sadece onay **sonrasında** oluşturulduğu için, onaylanmamış dokümanların RAG aramasına karışması tasarım gereği zaten engelleniyor (Faz 4'te join ile ek savunma katmanı eklendi).

**Faz 3 tamamlandı.**

---

## FAZ 4 — RAG Karar Mantığı (LangGraph)

**Kurulanlar:** `app/rag/retrieval.py` (`search_relevant_chunks` — pgvector `cosine_distance`, sadece `status='approved'` join'i, `company_id` filtresi), `app/rag/graph.py` (`RAGState`, `search_node`, `generate_answer_node`, `escalate_node`, `route_after_search`, `build_rag_graph`).

**Kavram notu:** pgvector'ün `cosine_distance()`'ı **mesafe** döndürür (0=benzer), Faz 1'deki **benzerlik** skorlarıyla (1=benzer) karşılaştırmak için `1 - mesafe` dönüşümü kullanılır.

**Doğrulama:** Sahte İK dokümanıyla test edildi — dokümanda olan soru doğru cevaplandı, dokümanda olmayan soru doğru şekilde `escalate` edildi (LLM'e hiç gidilmeden, hızlı).

**Faz 4 tamamlandı.**

---

## FAZ 5 — Celery + Redis Devreye Alma

**Kurulanlar:** `celery_app.py`, `app/tasks/document_tasks.py`, `app/tasks/rag_tasks.py`. API endpoint'leri artık iş mantığını kendileri yapmıyor, sadece `.delay()` ile task tetikliyor.

**Bulunup çözülen sorunlar:**
- `RAGState`'te `db_session` taşınamıyordu (Celery, görev parametrelerini JSON'a çevirmeye çalışıyor, bir DB bağlantısı JSON'a çevrilemez) → `db_session` State'ten kaldırıldı, `search_node` kendi session'ını açıp kapatıyor.
- Worker, task'ları hiç görmüyordu → `celery_app.py`'de `include=["app.tasks.document_tasks", "app.tasks.rag_tasks"]` eksikti, eklendi.

**Doğrulama:** Gerçek worker üzerinden hem belge işleme hem RAG akışı uçtan uca test edildi.

**Faz 5 tamamlandı.**

---

## FAZ 6 — E-posta Entegrasyonu

**Revize mimari kararı:** Postmark/SendGrid yerine **IMAP/SMTP doğrudan bağlantı** (gizlilik tutarlılığı için), **App Password** (OAuth2 değil), **Celery Beat polling** (webhook değil).

**Kurulanlar:**
- `app/email_service/reader.py` — `fetch_unseen_emails()` (IMAP `UNSEEN` + `BODY.PEEK[]` + MIME parse + charset-aware decode + `_strip_quoted_reply`).
- `app/email_service/processor.py` — iki katmanlı thread eşleştirme, `is_already_processed` (gerçek idempotency, `message_id_header` üzerinden).
- `app/email_service/sender.py` — SMTP gönderim, `In-Reply-To`/`References`, `EMAIL_DRY_RUN`.
- `app/tasks/email_tasks.py` — `process_single_email` (kaynaktan bağımsız, tekrar kullanılabilir) + `check_new_emails_task` (Redis dağıtık kilit + per-email hata izolasyonu).
- Celery Beat zamanlaması (`EMAIL_POLL_INTERVAL_SECONDS`).

**Bulunup çözülen gerçek sorunlar (kayda değer):**
1. IMAP `RFC822` fetch maili otomatik "okundu" işaretliyordu → `BODY.PEEK[]`.
2. Charset varsayımı (`utf-8` sabit) Türkçe karakterleri sessizce siliyordu → `part.get_content_charset()` kullanıldı.
3. İki paralel `check_new_emails` çalıştırması aynı maili işleyip `UniqueViolation` verdi (LLM'i bekleyen görev sürerken ikinci poll tetiklendi) → Redis `SET NX EX` ile dağıtık kilit.
4. Kilidin `finally`'de silinmesi unutulmuştu (iki kod parçası birleştirilirken bir satır kaybolmuş) → düzeltildi, "kodun gerçek halini gör" alışkanlığının değeri bir kez daha doğrulandı.
5. Outlook/Gmail'in "Yanıtla" ile eklediği alıntı bloğu soru metnine karışıyordu → regex tabanlı `_strip_quoted_reply()`.
6. Bu düzeltme ilk denemede çalışmadı — Outlook `\r\n` kullanıyordu, regex `\n` bekliyordu → önce `\r\n`/`\r` → `\n` normalizasyonu eklendi.

**Doğrulama:** Gerçek Gmail/Outlook hesapları arasında, çok sayıda senaryoyla (temiz soru, alıntılı takip, bilinmeyen konu, kıdem bazlı çıkarım, karma/sınır durumu) uçtan uca test edildi.

**Bilinen sınırlamalar:**
- Alıntı temizleme regex tabanlı, %100 kapsayıcı değil (gerçek üründe `talon` önerilir).
- Bilinmeyen domain'den gelen mailler sessizce atlanıyor, bildirim yok.
- `References` başlığı sadece son mesaj ID'sini taşıyor (standart gereği birikimli olmalıydı).
- Sadece Gmail App Password test edildi; OAuth2 ve Outlook/Exchange kurumsal IMAP hiç denenmedi.
- **Domain eşleştirmesi "1 domain = 1 şirket" varsayımına dayanıyor** — gerçek dünyada çalışanlar/stajyerler kişisel mail kullanabiliyor (örnek: Koton'da staj yaparken kişisel Outlook kullanımı), bu kişiler `unknown_domain` olarak atlanıp sistemle iletişim kuramıyor. Gerçek çözüm (`company_id`+tam e-posta tutan `authorized_senders` tablosu) MVP kapsamına alınmadı.
- **Paylaşılan/genel domain riski:** Küçük bir şirket `email_domain` olarak `gmail.com`/`outlook.com` gibi paylaşılan bir domain kaydederse, o domain'deki herkes yanlışlıkla o şirketin çalışanı sayılabilir — onboarding sürecinde engellenmesi gereken bir veri sızıntısı riski.
- **"Her gelen mail bir İK sorusudur" varsayımı** — niyet sınıflandırması (İK sorusu mu, başvuru mu, spam mı) yok.

**Faz 6 tamamlandı.**

---

## FAZ 7 — Next.js Paneli

**Öğrenme yaklaşımı:** Next.js/React deneyimi sıfırdan olduğu için her adımda önce izole/küçük bir doğrulama yapılıp üzerine inşa edildi.

**Kurulanlar:**
- **7.1-7.3:** Next.js iskeleti (TypeScript+Tailwind+App Router, `src/` klasörü yok), shadcn/ui, CORS (`allow_origins=["http://localhost:3000"]`).
- **7.4 — OCR Onay Ekranı:** `GET/PATCH /documents`, `StaticFiles` ile `uploads/` servisi, `/documents` liste, `/documents/[id]` detay (görsel+metin yan yana, düzenlenebilir `textarea`, ayrı "Kaydet"/"Onayla" butonları).
- **7.5 — `/test` Senaryo Simülasyon Paneli:** `test_emails.json` (22 senaryo), `process_single_email` ayrıştırıldı (kod tekrarını önlemek için), `POST /test/simulate/{index}` (`company_override` ile domain kontrolü atlanıyor).
- **7.6 — Belge Yönetimi:** Durum filtreli genel liste.
- **7.7 — Analitik:** `GET /analytics/summary` (toplam soru, escalation oranı, en çok yönlendirilen konular — `GROUP BY`).
- **UI Cilası:** Navbar (`components/navbar.tsx`, tüm sayfalarda ortak `layout.tsx`), belge yükleme formu (`/documents/upload`, `FormData` ile multipart), tüm sayfalara (`/documents`, `/documents/[id]`, `/test`, `/analytics`) hata durumu gösterimi (`.then/.catch` + kırmızı hata kutusu).

**Bulunup çözülen sorunlar:**
- `create-next-app`'ın güncel sürümü `src/` klasörü kullanmıyor (dokümantasyon varsayımından farklı).
- Orijinal dosya adı ile diskteki gerçek (UUID'li) dosya adı karıştırıldı → `Document.stored_filename` kolonu eklendi (migration).
- UTC tarihler frontend'de yerel saate çevrilmiyordu → API'den dönen tarihe `"Z"` eklendi.

**Bilinen sınırlamalar:**
- OCR onay ekranında sadece metin düzenlenebiliyor, görselin kendisi değil.
- `/analytics` ve `/test`'te `company_id` sabit kodlanmış.
- **Kimlik doğrulama (authentication) hiç yok** — hiçbir endpoint "bu isteği atan gerçekten bu şirkete mi ait" diye kontrol etmiyor. Gerçek ürün senaryosunda ilk yapılması gereken iyileştirmelerden biri; MVP kapsamı dışında bırakıldı.

**Faz 7 tamamlandı.**

---

## FAZ 8 — Test + Loglama + Config Doğrulama Altyapısı

**Motivasyon:** Faz 1-7 boyunca her şey elle/script'lerle test edildi — bu öğrenme açısından doğruydu, ama "bir şeyi bozdum mu" sorusunun cevabı hep "elle tekrar dene"ydi. Bu faz bunu otomatikleştirdi.

### Test Altyapısı

- **8.1** — Ayrı PostgreSQL test veritabanı (`ik_asistan_test_db`, pgvector eklentili — SQLite kullanılmadı, pgvector desteklemiyor). **Transactional rollback** stratejisi: her test kendi transaction'ında çalışır, sonunda hep `rollback()`. `alembic -x sqlalchemy.url=...` ile test DB'ye migration.
- **8.2** — Saf fonksiyon testleri (`chunk_text`, `_strip_quoted_reply`) — Faz 6.8'deki gerçek `\r\n` bug'ı **regresyon testine** çevrildi.
- **8.3** — `conftest.py` fixture'ları (`db_session`, `test_company`), thread eşleştirme/idempotency testleri. Bu süreçte **`datetime.utcnow()` deprecation** teknik borcu bulunup 6 dosyada (`models/company.py`, `document.py`, `email.py`, `email_service/processor.py`) `datetime.now(timezone.utc)` ile düzeltildi.
- **8.4** — FastAPI `TestClient` + `dependency_overrides` ile API testleri (`documents.py`).
- **8.5** — Mock (`unittest.mock.patch`) ile Ollama'dan bağımsız RAG karar mantığı testleri — Ollama kapalıyken bile geçtiği doğrulandı.
- **8.5.1-8.5.2** — Coverage raporu (`pytest --cov=app --cov-report=term-missing`) okunup boşluklar üç kategoriye ayrıldı (zaten gerçek testlerle kanıtlanmış dış-servis kodu / düşük maliyetli gerçek boşluklar / ağır iş). `PATCH`/`approve`/`sender` testleri eklendi. **Celery task testleri için "paylaşılan bağlantı" deseni** geliştirildi (`db_connection` + `test_session_factory` fixture'ları — task'ın kendi `SessionLocal()`'ı test transaction'ına `monkeypatch` ile bağlanıyor). Bu süreçte **ilk yazılan approve testi kırıldı** (Faz 5.4'te endpoint'in artık asenkron olduğunu, ilk testin ise eski senkron davranışı varsaydığını unutmuştuk) — düzeltilip hem endpoint hem task seviyesinde ayrı testler yazıldı.
- **Sonuç:** 27 test, tamamı ~2 saniyede çalışıyor. Genel coverage %63, kritik iş mantığı dosyalarında (`document_tasks.py`) %97'ye kadar.

### Loglama Altyapısı

- **8.6** — Merkezi `app/logging_config.py` (`get_logger(name)`, seviyeler: DEBUG/INFO/WARNING/ERROR/CRITICAL, `.env`: `LOG_LEVEL`).
- **8.7** — `email_tasks.py`'deki kritik `print()` → `logger.error(..., exc_info=True)` (traceback dahil).
- **8.8** — `RotatingFileHandler` (`logs/app.log`, 5MB × 4 dosya) — hem terminale hem kalıcı dosyaya yazıyor. `sender.py`'deki DRY_RUN `print()`'lerine bilinçli olarak dokunulmadı (kullanıcıya konsol çıktısı amacı taşıyor, loglama değil; ayrıca `capsys` ile test ediliyor).

### Config Doğrulama

- **8.9** — `app/config.py` — `pydantic-settings` ile `.env` doğrulaması. Zorunlu alanlar eksikse **fail-fast**: `main.py`/`celery_app.py` başlamadan, hangi alanın eksik olduğunu açıkça söyleyen bir `ValidationError`. `EMAIL_DRY_RUN` gibi bool alanlar artık elle string-parse edilmiyor.
- **8.10** — Config doğrulaması için testler (`Settings` başarıyla yükleniyor mu, eksik alanda doğru hata veriyor mu, bool parse doğru mu).

**Faz 8 tamamlandı.**

---

## Groundedness Check (RAG Kalite İyileştirmesi)

**Motivasyon:** Faz 4'te kurduğumuz güven eşiği (`RAG_CONFIDENCE_THRESHOLD`), sadece "alakalı chunk bulundu mu" sorusuna cevap veriyor — üretilen cevabın **gerçekten** o chunk'ın içeriğiyle tutarlı olduğunu garanti etmiyor. Bu, en başından beri ("reranker/groundedness check yok" maddesi) bilinen bir sınırlamaydı.

**Uygulanan çözüm (ek model/altyapı olmadan):** `app/rag/graph.py`'ye yeni bir node — `groundedness_check_node`. `generate_answer_node`'un ürettiği cevap, doğrudan kullanıcıya gitmeden önce, **aynı LLM'e ikinci bir çağrıyla** ("bu cevap kaynak metinde gerçekten var mı? EVET/HAYIR") sorgulanıyor. `HAYIR` cevabı gelirse, akış **mevcut `escalate_node`'a** yönlendiriliyor (kod tekrarı yok). `.env`: `GROUNDEDNESS_CHECK_ENABLED` ile açılıp kapatılabiliyor.

**Yeni akış:**
```
search → (eşik üstü mü?) → generate_answer → groundedness_check → (destekleniyor mu?) → EVET → END
                                                                                        → HAYIR → escalate → END
                          → escalate → END
```

**Bulunan/doğrulanan davranış:** Celery worker, kod değişikliklerini otomatik yenilemiyor (bkz. Genel Kurallar #9) — groundedness node'u eklendikten sonra worker yeniden başlatılmadan test edilince, eski kod çalışmaya devam etmiş ve tek `api/chat` çağrısı görülmüştü. Sistem yeniden başlatılınca iki ayrı `api/chat` çağrısı (cevap üretimi + groundedness kontrolü) doğrulandı.

**Kritik bulgu — "thinking" modu boş cevaba yol açıyordu (Faz 1'den beri var olan, gizli bir sorun):** İkinci demo şirketle (Faz 9.1) test edilirken, hem `generate_answer_node` hem `groundedness_check_node`'un **boş içerik** (`content=""`) döndürdüğü, akışın her seferinde `escalate`'e düştüğü ve çağrıların 30-95 saniye sürdüğü görüldü. **Kök neden:** `qwen3.5:9b`, Ollama'da varsayılan olarak "thinking" modunda çalışıyor — cevabı üretmeden önce görünmez bir `<think>...</think>` bloğu içinde muhakeme yürütüyor, bu da **`num_ctx` bütçesinden pay alıyor.** `num_ctx=4096`'ya (Faz 1'de VRAM optimizasyonu için) düşürülmüş olması, art arda iki çağrıda (özellikle groundedness gibi kendi başına muhakeme gerektiren bir soruda) düşünme sürecinin **bütçenin tamamını tüketip** gerçek cevaba hiç yer bırakmamasına yol açabiliyordu. Bu, Faz 1 ve Faz 6'da gözlemlenen ama o zaman kaynağı bilinmeyen ara sıra boş cevap / garip karakter sızıntısı olaylarını da açıklıyor.

**Çözüm:** Ollama'nın `client.chat(...)` çağrısına `think=False` parametresi eklendi (hem `generate_answer_node` hem `groundedness_check_node`'da) — model düşünme adımını atlayıp doğrudan cevap üretiyor. Sonuç: çağrı süreleri 30-95 saniyeden **4-6 saniyeye** düştü, boş cevap sorunu ortadan kalktı. **Genel kural olarak kaydedildi** (bkz. Genel Kurallar): Qwen3 ailesi modellerle yapılan her `chat()` çağrısında `think=False` açıkça belirtilmeli.

**İkinci bulgu — groundedness check'in yanlış negatif (false negative) vermesi:** `think=False` sonrası, dokümanda kısmen bilgi olan bir soruda ("25 gün" bilgisi var, "tek seferde kullanım" bilgisi yok), model **dürüstçe** "bu konuda bilgi yok" diyen iyi bir cevap üretti — ama groundedness check bunu `HAYIR` olarak işaretleyip escalate'e yönlendirdi. **Kök neden (iki parça):** (1) Prompt, "kaynakta birebir yer almayan her şeyi" ihlal sayacak şekilde katıydı — modelin dürüst "bilgi yok" ifadesini de ihlal sanmış olabilir. (2) Çağrıda `temperature` ayarlanmamıştı — güvenlik kritikliği olan bir karar rastgeleliğe açıktı. **Çözüm:** Prompt'a "dürüst bilgi eksikliği beyanı ihlal değildir" kuralı eklendi, `temperature=0` ile karar determinize edildi. **Doğrulama:** Aynı senaryo 5 kez art arda çalıştırılıp 5/5 tutarlı `EVET` (doğru karar) alındı.

**Testler:** 5 yeni test (`GROUNDEDNESS_CHECK_ENABLED=false` iken LLM'e hiç gidilmediği, `EVET`/`HAYIR` yanıtlarının doğru parse edildiği, yönlendirme fonksiyonu) — toplam test sayısı 32'ye çıktı.

**Maliyet notu:** Her `generate_answer` çağrısı artık **iki katına** çıkıyor (asıl cevap + doğrulama) — `escalate` yoluna hiç etkisi yok, çünkü o yol zaten LLM çağırmıyor.

---

## FAZ 9 — Multi-Tenant Sıkılaştırma (Kısmi Kapsamla Sonlandırıldı)

**Test şirketleri:**
- A Şirketi (orijinal): `4d3ef371-7d0e-4111-91d0-aa8ffe7e0188` — izin politikası (1 yıl sonra hak, 1-5 yıl kıdem→14 gün, 5+ yıl→20 gün).
- B Şirketi (Faz 9.1'de eklendi): `e5e5fa0d-2b04-4a08-b210-915ad9d85e5f`, doküman ID `4e711598-bf6e-4764-be3b-18f818378655` — bilinçli olarak farklı sayılarla (6 ay sonra hak, kıdeme bakılmaksızın 25 gün, 1 hafta önceden talep) izolasyon testlerinde karışıklığı kolayca fark edebilmek için.

**Tamamlanan:**
- **9.1** — İkinci şirket + farklı içerikli doküman oluşturuldu.
- **9.2** — Manuel izolasyon testi (B şirketi sorgusu doğru şekilde sadece B'nin verisini kullandı, A'nın hiçbir sayısı karışmadı) + otomatik pytest testleri (`test_retrieval.py` — `search_relevant_chunks`'ın şirketler arası hiç karışmadığını ve onaysız dokümanların çok şirketli ortamda da göz ardı edildiğini kanıtlıyor).
- Bu süreçte **iki önemli, projenin genelini ilgilendiren LLM bug'ı** bulunup düzeltildi (bkz. Groundedness Check bölümü): `think=False` zorunluluğu ve groundedness prompt'unun determinizmi (`temperature=0`).

**Bilinçli olarak kapsam dışı bırakılan (RLS yorgunluğu/karmaşıklık nedeniyle durma kararı):**
- **9.3 — PostgreSQL Row Level Security (RLS):** Tasarımı konuşuldu (`FORCE ROW LEVEL SECURITY` gerekliliği, `set_company_context()` mekanizması, `GET /documents`/`GET /documents/{id}`'nin şu an `company_id` filtrelemediği bulgusu dahil) ama **uygulanmadı.** İzolasyon şu an sadece **uygulama seviyesinde** (`WHERE company_id=`, artık testlerle de doğrulanmış) — veritabanı seviyesinde ikinci bir savunma katmanı yok. Bilinçli bir kapsam kararı: bu proje bir portföy/öğrenme projesi, RLS kendi başına ayrı bir öğrenme konusu olarak not edildi.
- **9.6 — Genel hata yönetimi gözden geçirmesi (global exception handler):** Hiç başlanmadı.
- **9.7 — README:** Kapsam dışına alındı — proje kapanışında (genel değerlendirme adımında) ele alınacak.
- **Yan bulgu, henüz düzeltilmedi:** `GET /documents` ve `GET /documents/{id}` endpoint'leri `company_id`'ye göre filtrelemiyor — teorik olarak `document_id`'sini bilen biri başka bir şirketin belgesini görebilir (UUID'nin tahmin edilemezliğine güveniyor, gerçek bir erişim kontrolü yok). RLS uygulanmadığı için bu açık kapalı kalmadı.

**Faz 9, bu kapsamla sonlandırıldı.**

---

## `requirements.txt` + CI/CD (GitHub Actions)

**Kurulanlar:**
- `backend/requirements.txt` — doğrudan kurulan paketler, gruplandırılmış ve versiyonlanmış (`pip freeze` çıktısından, gerçek `.venv`'den alınan sürümlerle). Alt bağımlılıklar elle listelenmedi, `pip`'e bırakıldı.
- `.github/workflows/tests.yml` — GitHub Actions CI (sadece CI, **CD/deploy kapsamda değil** — bilinçli bir tercih, ayrı bir projede deploy deneyimi kazanılması kararıyla tutarlı). `main`'e her push/PR'da: Postgres+pgvector ve Redis service container'ları (health-check ile hazır olma garantisi) → bağımlılık kurulumu → `alembic upgrade head` → `pytest tests/ -v --cov`.

**Bilinçli tasarım kararları:**
- CI ortamında **gerçek** kimlik bilgileri kullanılmıyor — `.env`'deki zorunlu alanlar (Faz 8.9 `pydantic-settings` doğrulaması nedeniyle) sahte ama biçimsel olarak geçerli değerlerle (`EMAIL_APP_PASSWORD: dummy-password-for-ci` gibi) dolduruluyor. Hiçbir test gerçekten bu değerlerle bir yere bağlanmıyor.
- Ollama/GPU, CI runner'ında **hiç yok** — bu sorun değil, çünkü Faz 8'de kurduğumuz mock stratejisi sayesinde testlerin hiçbiri gerçek bir Ollama bağlantısı gerektirmiyor (Faz 8.5'te Ollama kapalıyken bile geçtiği zaten doğrulanmıştı).
- Frontend (Next.js) CI kapsamına alınmadı — hiç otomatik test yazılmadı (bilinen sınırlama).
- PostgreSQL'e CI'da `localhost` üzerinden erişiliyor — yerel WSL2/`host.docker.internal` ayrımı burada geçerli değil, GitHub'ın kendi altyapısında servis container'ları doğrudan erişilebilir.

**Doğrulama:** İlk push'ta ilk denemede başarılı (yeşil) — 34 test, 58 saniyede tamamlandı.

---

## FAZ 10 — Docker (Uygulamanın Kendisini Container'lama)

**Motivasyon:** Faz 0'dan beri sadece **altyapı** (Postgres, Redis) Docker'daydı; FastAPI/Celery/Next.js hâlâ yerel `.venv`/`npm run dev` ile çalışıyordu. Bu faz, tüm sistemi tek komutla (`docker compose up`) ayağa kalkacak hale getirdi.

**Kurulanlar:**
- `backend/Dockerfile` — tek aşamalı (`python:3.12-slim`). `api`, `worker`, `beat`, `migrate` **aynı image'ı** kullanıyor, sadece `command:` farklı (gereksiz tekrar yok).
- `frontend/Dockerfile` — **multi-stage build** (`deps` → `builder` → `runner`), Next.js'in `output: "standalone"` modu ile. Sonuç: 358MB (backend 716MB'a kıyasla belirgin küçük).
- `docker-compose.yml` genişletildi: `migrate` (tek seferlik, `service_completed_successfully` ile diğerlerinin beklediği), `api`, `worker`, `beat`, `frontend` servisleri + Postgres/Redis health check'leri.
- `db/init/01-enable-pgvector.sql` — `docker-entrypoint-initdb.d` mekanizmasıyla, veritabanı ilk oluşturulduğunda `CREATE EXTENSION vector` **otomatik** çalışıyor (Faz 2'den beri elle tekrarladığımız adım kalıcı olarak otomatikleşti).

**Bulunup çözülen sorunlar:**
1. **`type "vector" does not exist`** — `docker compose down -v` sonrası temiz volume'da pgvector eklentisi hiç etkinleştirilmemişti → `db/init/` betiğiyle kalıcı olarak otomatikleştirildi.
2. **`database "ik_asistan" does not exist` (log gürültüsü)** — `pg_isready -U ik_asistan` komutu, `-d` verilmediğinde kullanıcı adıyla aynı isimli bir veritabanı arıyor. **Önemli not:** `pg_isready` aslında veritabanına **hiç bağlanmıyor** (PostgreSQL dokümantasyonu), sadece sunucunun yanıt verip vermediğine bakıyor — yani bu mesaj health check'i hiç etkilemiyordu, sadece log gürültüsüydü. `-d postgres` eklenerek susturuldu.
3. **`extra_hosts: host.docker.internal:host-gateway` eklememiz, Ollama bağlantısını BOZDU.** Docker Desktop (Windows/WSL2), `host.docker.internal`'i **zaten otomatik ve doğru** çözüyor; `host-gateway` özel değeri ise container'ın kendi köprü ağı geçidine işaret ediyor (orada Ollama yok → `Connection refused`). **Ders: Docker Desktop'ta bu satır gereksiz, hatta zararlı.** Kaldırılınca bağlantı düzeldi. (Native Linux Docker'da ise gerekli — ayrım önemli.)
4. **Frontend'e bağlanılamaması** — container içinde Next.js'in dinlediği port ile compose'daki eşleştirme arasında uyumsuzluk (yerelde `5300` kullanılıyormuş). Tüm port referansları `3000`'e hizalanarak çözüldü. **Ders:** Bu tür "bağlanamıyorum" durumlarında `docker compose logs <servis>` en hızlı teşhis aracı — sunucular başlarken hangi portu dinlediklerini kendileri loglar.

**Öğrenilen kavramlar:** Multi-stage build (derleme araçlarını nihai image'dan atma), `npm ci` vs `npm install` (tekrarlanabilirlik), Docker katman önbelleği (`COPY requirements.txt` → `pip install` → `COPY . .` sıralamasının nedeni), content-addressable storage (aynı image'ın farklı tag'lerinin diskte tek kopya durması).

**Bilinen sorun (çözülmedi):** `run_dev.sh`/`stop_dev.sh` (Honcho+tmux geliştirme ortamı), artık `docker-compose.yml`'de `api`/`worker`/`beat`/`frontend` servisleri de bulunduğu için **çakışıyor** — `run_dev.sh` çalıştırıldığında hem container'daki hem Honcho'daki servisler aynı portları isteyecek. Çözüm yolu konuşuldu (Docker Compose `profiles` özelliğiyle servisleri etiketlemek) ama **uygulanmadı** — proje Docker moduna geçtiği için bu script'lere pratik ihtiyaç kalmadı, ileride ayrıca ele alınmak üzere bırakıldı.

**Faz 10 tamamlandı.**

---

## Bilinen Sınırlamalar (Genel Özet)

Proje boyunca bulunan, bilinçli olarak MVP kapsamı dışında bırakılan noktaların toplu listesi (detaylar ilgili faz bölümlerinde):

1. Kimlik doğrulama (authentication) hiç yok — `company_id` sabit kodlanmış.
2. Domain eşleştirmesi "1 domain = 1 şirket" varsayımına dayanıyor; kişisel mail kullanan çalışanlar/stajyerler sistemle iletişim kuramıyor.
3. Paylaşılan/genel domain (`gmail.com` vb.) bir şirketin domain'i olarak kaydedilirse veri sızıntısı riski oluşur.
4. "Her gelen mail bir İK sorusudur" varsayımı — niyet sınıflandırması yok.
5. Alıntı temizleme (%100 kapsayıcı değil), `References` başlığı birikimli değil.
6. Sadece Gmail/App Password test edildi; OAuth2, Outlook/Exchange kurumsal IMAP denenmedi.
7. Gerçek bir reranker modeli yok — sadece groundedness check (aynı LLM ile ikinci doğrulama) eklendi; cross-encoder tabanlı ayrı bir reranker, ek VRAM maliyeti nedeniyle bilinçli olarak eklenmedi.
8. KVKK/veri saklama-silme politikası uygulanmadı.
9. RLS henüz yok (Faz 9'da bilinçli olarak ertelendi) — sadece uygulama seviyesi (`WHERE company_id=`) filtreleme, artık testlerle doğrulanmış durumda.
10. OCR onay ekranında sadece metin düzenlenebiliyor, görsel değil.
11. Uygulamanın kendisi container'landı (Faz 10) — ancak `run_dev.sh`/`stop_dev.sh` (Honcho+tmux geliştirme ortamı) artık compose ile **çakışıyor**, `profiles` çözümü uygulanmadı.
12. `httpx2` gibi sonradan eklenen bağımlılıklar `requirements.txt`'te — `honcho`/`tmux` da orada, ancak `tmux` bir sistem paketi olarak README'de belirtilmeli.
13. `GET /documents` ve `GET /documents/{id}` endpoint'leri `company_id`'ye göre filtrelemiyor — teorik olarak `document_id`'sini bilen biri başka bir şirketin belgesini görebilir. RLS uygulanmadığı için bu, veritabanı seviyesinde de kapatılmadı.
14. Global bir exception handler / genel hata yönetimi gözden geçirmesi yapılmadı (Faz 9'un bir parçası olarak planlanmıştı, kapsam dışına alındı).
15. Chunk'lama naif (`\n\n` ile paragraf bölme + `min_length` filtresi) — semantik/başlık hiyerarşisine duyarlı bir bölme yapılmadı.
16. `RAG_CONFIDENCE_THRESHOLD` (0.55) hiç gerçek ölçekte kalibre edilmedi — Faz 1'deki üç örnek cümlelik ölçümden gelen bir başlangıç tahmini.
17. Test şirketleri ve dokümanları **elle** (`psql` + `seed_test_hr_data.py`) oluşturuluyor — tekrarlanabilir bir seed/fixture betiği yok, `docker compose down -v` sonrası hepsi kayboluyor.

---

## Kod Asistanları İçin Genel Kurallar

1. **Faz sırasını atlama.** Her faz bir öncekinin üzerine kurulu.
2. **Bölüm 0'daki teknoloji kararlarını sorgulama/değiştirme** — bu kararlar tartışılıp gerekçelendirilmiş, çoğu gerçek testlerle doğrulanmıştır.
3. Proje kodu her zaman WSL2/Ubuntu dosya sisteminde (`~/projects/ik-asistan`), Windows tarafında (`/mnt/c/...`) değil.
4. Ollama çağrıları `OLLAMA_BASE_URL`/`app.config.settings` üzerinden yapılmalı, adres kod içine sabit yazılmamalı.
5. Yeni bir model eklendiğinde `app/models/__init__.py`'ye eklenmeli (aksi halde SQLAlchemy foreign key'i tanımaz — Faz 3'te yaşanan hata).
6. Yeni bir Celery task dosyası eklendiğinde `celery_app.py`'deki `include=[...]` listesine eklenmeli (aksi halde worker task'ı görmez — Faz 5'te yaşanan hata).
7. Yeni kod yazıldığında, mümkünse aynı PR/adımda bir test de eklenmeli (Faz 8'den itibaren kurulu standart).
8. `datetime.now(timezone.utc)` kullanılmalı, `datetime.utcnow()` değil (deprecated, Faz 8.3'te düzeltildi).
9. **Celery worker, kod değişikliklerini otomatik yenilemez.** `uvicorn --reload` sadece FastAPI/web sürecini kapsar — `app/rag/`, `app/tasks/`, `app/email_service/` gibi worker tarafından kullanılan dosyalarda değişiklik yapıldığında, worker'ın belleğindeki eski kodu değil yeni kodu kullanması için sistem yeniden başlatılmalı (`stop_dev.sh` + `run_dev.sh`).
10. **Qwen3 ailesi modellerle (`qwen3.5:9b` dahil) yapılan her `client.chat(...)` çağrısında `think=False` açıkça belirtilmeli.** Varsayılan "thinking" modu, `num_ctx` bütçesinden pay alıyor — düşük `num_ctx` (bizde 4096) ile birleşince, özellikle art arda/zincirleme çağrılarda (örn. groundedness check) düşünme süreci tüm bütçeyi tüketip **boş cevaba** yol açabiliyor (Faz 1 ve Faz 6'daki açıklanamayan boş cevap/garip karakter olaylarının kök nedeni bu). `think=False`, hem bu riski ortadan kaldırıyor hem de yanıt süresini ciddi şekilde kısaltıyor (gözlemlenen: 30-95 saniyeden 4-6 saniyeye).
11. **Güvenlik/karar kritikliği olan LLM çağrılarında (`groundedness_check_node` gibi) `temperature=0` kullanılmalı** — rastgelelik, aynı girdiye farklı kararlar (tutarsız EVET/HAYIR) verilmesine yol açabilir.

## Git Commit Alışkanlığı

Her **anlamlı bütünlük oluşturan alt adımda** commit atılır — her küçük dosya değişikliğinde değil.

**Mesaj formatı:** `"Faz X.Y: [ne yapıldı, kısa]"` — örnek: `"Faz 8.6: Merkezi logging yapılandırması eklendi"`.

```bash
git status              # .env, .venv/, node_modules/, logs/ görünmemeli
git add .
git commit -m "Faz X.Y: ..."
```

## Proje Kapanış Değerlendirmesi

**Projenin niteliği:** Bitmiş bir **portföy/öğrenme projesi**. Eksiksiz bir ticari ürün değil — ve zaten öyle olması hedeflenmedi. Kapsam sınırları bilinçli çizildi ve her biri gerekçesiyle belgelendi.

### Güçlü Yanlar

- **Gerçek koşullarda kanıtlanmış çekirdek işlevsellik** — sistem, gerçek Gmail/Outlook hesapları arasında, gerçek e-posta protokolüyle, çok sayıda senaryoyla test edildi. Faz 6'daki `\r\n`, charset, IMAP `PEEK` gibi bulgular yalnızca gerçek testlerde ortaya çıkabilecek türdendi.
- **Bilinçli güvenlik tasarımı** — insan onayı (düzenlenebilir OCR çıktısıyla), halüsinasyona karşı iki katmanlı savunma (güven eşiği + groundedness check), şirket bazlı izolasyon (testlerle kanıtlanmış), idempotency, dağıtık kilit.
- **Mühendislik disiplini katmanları** — 34 otomatik test (mock ile dış servislerden bağımsız), CI (GitHub Actions), yapılandırılmış loglama, fail-fast config doğrulama, tam container'ize sistem.
- **Belgelenmiş hata/çözüm geçmişi** — `think=False` bulgusu (Faz 1'den beri gizli duran sorunun iki faz sonra doğru teşhisi), race condition'ın gerçek koşullarda ortaya çıkışı ve çözümü, `extra_hosts`'un fayda değil zarar verdiğinin keşfi. Bu geçmiş, projenin en öğretici kısmı.

### Zayıf Yanlar / Eksikler

Detaylı liste yukarıdaki "Bilinen Sınırlamalar" bölümünde. En kritik üçü:
1. **Kimlik doğrulama yok** — sistemi gerçek bir çok-kullanıcılı ürün olmaktan alıkoyan en büyük eksik.
2. **RLS yok** — izolasyon sadece uygulama katmanında (test edilmiş ve çalışıyor, ama ikinci savunma hattı yok).
3. **RAG kalitesinde naif noktalar** — basit chunk'lama, kalibre edilmemiş eşik, gerçek reranker yokluğu.

### Gelecekteki Projeler İçin Not Alınan Konular

Bu projede bilinçli olarak kapsam dışı bırakılan, ayrı/daha sade projelerde öğrenilmesi daha sağlıklı bulunan konular: **kimlik doğrulama (JWT/oturum yönetimi)**, **PostgreSQL Row Level Security**, **gerçek bir sunucuya deploy (CD)**.

---

## Şu Anki Durum / Devam Noktası

**Tamamlanan:** Faz 0-10'un tamamı + Groundedness Check + CI. Proje **kapatıldı**.
**Kapsam dışı bırakılan (bilinçli karar):** Kimlik doğrulama, gerçek sunucuya deploy, PostgreSQL RLS, global exception handler — hepsi "Bilinen Sınırlamalar" listesinde gerekçeleriyle kayıtlı.

**Projeye yeni bakan biri için giriş noktası:** `README.md` (kurulum + kullanım), ardından `Proje_Dokumantasyonu.md` (mimari gerekçeler), ardından bu dosya (uygulama geçmişi ve alınan kararlar).