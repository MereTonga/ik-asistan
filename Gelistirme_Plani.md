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
| 9 | Multi-Tenant Sıkılaştırma + Cila | ⏳ Sırada |
| — | `requirements.txt` + CI/CD (GitHub Actions) | Planlandı |
| — | Docker (uygulamanın kendisini container'lama) | Planlandı |
| — | Genel değerlendirme (tüm `.md` dosyalarının son güncellemesi) | Planlandı |

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

**Testler:** 5 yeni test (`GROUNDEDNESS_CHECK_ENABLED=false` iken LLM'e hiç gidilmediği, `EVET`/`HAYIR` yanıtlarının doğru parse edildiği, yönlendirme fonksiyonu) — toplam test sayısı 32'ye çıktı.

**Maliyet notu:** Her `generate_answer` çağrısı artık **iki katına** çıkıyor (asıl cevap + doğrulama) — `escalate` yoluna hiç etkisi yok, çünkü o yol zaten LLM çağırmıyor.

---

## FAZ 9 — Multi-Tenant Sıkılaştırma + Cila (Sırada)

**Yapılacaklar (orijinal plan, henüz başlanmadı):**
- İkinci bir demo şirket eklenip `company_id` izolasyonunun gerçekten test edilmesi.
- PostgreSQL Row Level Security (RLS) eklenmesi.
- Genel hata yönetimi gözden geçirmesi.
- README.

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
9. RLS henüz yok — sadece uygulama seviyesi (`WHERE company_id=`) filtreleme.
10. OCR onay ekranında sadece metin düzenlenebiliyor, görsel değil.
11. Uygulamanın kendisi (FastAPI/Next.js) container'lanmadı — sadece altyapı servisleri (Postgres/Redis) Docker'da.
12. `honcho`/`tmux`/`httpx2` gibi bağımlılıklar henüz bir `requirements.txt`'te belgelenmedi.

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

## Git Commit Alışkanlığı

Her **anlamlı bütünlük oluşturan alt adımda** commit atılır — her küçük dosya değişikliğinde değil.

**Mesaj formatı:** `"Faz X.Y: [ne yapıldı, kısa]"` — örnek: `"Faz 8.6: Merkezi logging yapılandırması eklendi"`.

```bash
git status              # .env, .venv/, node_modules/, logs/ görünmemeli
git add .
git commit -m "Faz X.Y: ..."
```

## Şu Anki Durum / Devam Noktası

**Tamamlanan:** Faz 0-8 (tamamı) + Groundedness Check.
**Sırada:** Faz 9 — Multi-Tenant Sıkılaştırma + Cila (ikinci demo şirket, RLS, hata yönetimi, README).
**Sonraki planlanan adımlar (kararlaştırılmış sıra):** Faz 9 → `requirements.txt` + CI/CD (GitHub Actions) → Docker (uygulamanın kendisini container'lama) → Genel değerlendirme (tüm `.md` dosyalarının son güncellemesi).
**Kapsam dışı bırakılan (bilinçli karar):** Kimlik doğrulama (authentication) ve gerçek bir sunucuya deploy — ikisi de projenin mevcut karmaşıklığına (çok süreçli mimari, GPU bağımlılığı, kişisel e-posta hesabı) göre ayrı, daha sade projelerde öğrenilmesi daha sağlıklı bulunan konular olarak not edildi.

Yeni bir sohbette kaldığımız yerden devam edilecekse: bu dosya (`Gelistirme_Plani.md`) ve `Proje_Dokumantasyonu.md` yeterlidir.