# Yapay Zeka Destekli Dijital İK E-Posta Asistanı

## Kapsamlı Sistem ve Karar Gerekçeleri Dokümanı

> **Bu doküman nedir?** Bu proje henüz kurulum/kodlama aşamasına geçmemiş bir tasarım dokümanıdır. Amacı, projeyi hiç duymamış birinin bile ne yapıldığını, nasıl çalıştığını ve *neden* bu teknolojilerin seçildiğini anlayabilmesidir. Ayrıca bu proje, satılabilir bir ticari ürün değil; **portföy/CV amaçlı, gerçek bir production sisteminin tasarım disipliniyle geliştirilen bir gösterim (showcase) projesidir.** Bu ayrım, ilerleyen bölümlerde bazı kararların neden "ideal" değil "yeterince iyi ve gerçekçi" seçildiğini açıklar.

---

## İçindekiler

1. [Proje Vizyonu ve Kapsamı](#1-proje-vizyonu-ve-kapsamı)
2. [Problem Tanımı (Teknik Olmayan Anlatım)](#2-problem-tanımı-teknik-olmayan-anlatım)
3. [Çözüm Özeti](#3-çözüm-özeti)
4. [Genel Sistem Mimarisi](#4-genel-sistem-mimarisi)
5. [Teknoloji Yığını ve Seçim Gerekçeleri](#5-teknoloji-yığını-ve-seçim-gerekçeleri)
6. [Yapay Zeka Model Stratejisi](#6-yapay-zeka-model-stratejisi)
7. [Sistem Akışı: 5 Operasyonel Aşama](#7-sistem-akışı-5-operasyonel-aşama)
8. [Detaylı Veri Akış Şemaları](#8-detaylı-veri-akış-şemaları)
9. [Güvenlik ve Çok Kiracılı (Multi-Tenant) İzolasyon](#9-güvenlik-ve-çok-kiracılı-multi-tenant-izolasyon)
10. [Performans ve Ölçeklenebilirlik Değerlendirmesi](#10-performans-ve-ölçeklenebilirlik-değerlendirmesi)
11. [Bilinen Sınırlamalar ve Gerçek Ürüne Dönüşürse Yapılması Gerekenler](#11-bilinen-sınırlamalar-ve-gerçek-ürüne-dönüşürse-yapılması-gerekenler)
12. [Proje Kapsamı: MVP ve Uzun Vadeli Vizyon](#12-proje-kapsamı-mvp-ve-uzun-vadeli-vizyon)
13. [Sözlük](#13-sözlük)

---

## 1. Proje Vizyonu ve Kapsamı

**Ne yapılıyor?** Şirket içi İK (İnsan Kaynakları) dokümantasyonunu (izin politikası, mesai kuralları, uzaktan çalışma prosedürleri vb.) yapay zeka ile dijitalleştirip, çalışanların bu konularda e-posta ile sorduğu soruları otomatik ama **güvenilir** şekilde yanıtlayan bir sistem.

**Neden yapılıyor?** Bu proje, birincil olarak bir **beceri gösterim projesi (portfolio project)**dir:

- Backend geliştirme (FastAPI, asenkron mimari)
- Yapay zeka orkestrasyonu (RAG, LangGraph, lokal LLM çalıştırma)
- Sistem tasarımı (kuyruk mimarisi, çok kiracılı veri izolasyonu, webhook entegrasyonu)
- Üretim düşüncesi (güvenlik, hukuki risk, ölçeklenebilirlik farkındalığı)

konularının **hepsini tek bir tutarlı, gerçekçi senaryoda** bir araya getirmek amacıyla tasarlanmıştır. Gerçek bir şirkete satılacak bir SaaS ürünü **değildir** — ama öyleymiş gibi, aynı ciddiyetle tasarlanmıştır. Bu nedenle doküman boyunca hem "bunu neden böyle yaptık" hem de "gerçek bir ürün olsaydı bu noktada ne eksik kalırdı" notları birlikte yer almaktadır.

---

## 2. Problem Tanımı (Teknik Olmayan Anlatım)

Bir şirkette çalışan biri genellikle şu tarz sorular sorar:

- *"Yıllık izin hakkım ne zaman başlıyor?"*
- *"Mesai ücreti ödeniyor mu, nasıl hesaplanıyor?"*
- *"Uzaktan çalışma kuralımız nedir, haftada kaç gün ofise gelmem gerekiyor?"*

Bu soruların cevapları genellikle bir yerde **yazılıdır** — ama çoğu zaman:

- Kağıt üzerinde, dolapta duran bir belgede,
- Taranmış ama düzenlenemeyen bir PDF'te,
- Ya da sadece İK çalışanının hafızasındadır.

Sonuç: İK departmanı, günün önemli bir kısmını **aynı soruları tekrar tekrar cevaplayarak** geçirir. Bu hem İK için zaman kaybı, hem çalışan için "cevap ne zaman gelecek" belirsizliğidir.

---

## 3. Çözüm Özeti

Sistem dört ana adımda çalışır:

1. **Belgeyi dijitalleştir:** İK yöneticisi kural kağıdının fotoğrafını çeker/yükler, yapay zeka bunu düzenli bir metne çevirir.
2. **İnsan onayı al:** Yapay zeka çıktısı otomatik olarak yayına alınmaz — bir insan (İK yetkilisi) kontrol edip onaylar. *(Neden? Çünkü OCR bir sayıyı yanlış okursa — örneğin "%50" yerine "%5" — bu hukuki bir hataya dönüşebilir.)*
3. **Soruyu e-postadan yakala:** Çalışan `ik@sirket.com` adresine mail attığında sistem bunu otomatik yakalar.
4. **Cevapla veya yönlendir:** Sistem, onaylanmış dokümanlarda soruya net bir cevap varsa kibar bir e-posta taslağı hazırlar. Cevap yoksa **uydurmaz** — soruyu gerçek bir İK çalışanına yönlendirir.

---

## 4. Genel Sistem Mimarisi

```
+---------------------------------------------------------------------------------------+
|                                1. FRONTEND KATMANI                                    |
|   [ Next.js Web Paneli ]  <--->  [ Markdown/MDX Editörü ]  <---> [ Görsel Karşılaştırma ] |
+-------------------------------------------+-------------------------------------------+
                                             |
                                             |  HTTPS / REST API
                                             v
+---------------------------------------------------------------------------------------+
|                                2. BACKEND KATMANI                                     |
|                               [ FastAPI Framework ]                                   |
|   +-----------------------+-----------------------+-------------------------------+   |
|   | Auth & Tenant Guard    | Ingestion Controller  | E-posta Webhook Dinleyici     |   |
|   +-----------------------+-----------------------+-------------------------------+   |
+-------------------+---------------------------------------+---------------------------+
                    |                                       |
        Görev Atama (Asenkron)                    Gelen / Giden JSON
                    v                                       v
+---------------------------------------+   +-------------------------------------------+
|          3. KUYRUK & WORKER            |   |            4. E-POSTA SERVİSİ             |
|           [ Redis Broker ]             |   |   [ Postmark / SendGrid Inbound Parse ]   |
|                   |                    |   +-------------------------------------------+
|                   v                    |
|        [ Celery Worker Havuzu ]        |
+-------------------+--------------------+
                    |
        +-----------+---------------------------------------+
        |                                                    |
        v                                                    v
+---------------------------------------+   +-------------------------------------------+
|         5. LOKAL YAPAY ZEKA / GPU     |   |          6. VERİTABANI KATMANI            |
|            [ Ollama Sunucusu ]         |   |          [ PostgreSQL Sunucusu ]          |
|  +----------------------------------+ |   |  +---------------------------------------+ |
|  | OCR/Görsel: qwen3-vl              | |   |  | İlişkisel: Tenant, Users, Threads,   | |
|  | LLM (metin üretimi): qwen3.5      | |   |  |            E-posta Mesajları, Loglar | |
|  | Embedding: qwen3-embedding        | |   |  +---------------------------------------+ |
|  +----------------------------------+ |   |  | Eklenti: pgvector                    | |
|                                        |   |  | (Doküman Parçaları & Vektör İndeksi)  | |
+----------------------------------------+   |  +---------------------------------------+ |
                                             +-------------------------------------------+
```

**Katmanların birbirine bağlanma mantığı:**

- Frontend, backend'e sadece HTTPS/REST üzerinden konuşur — arayüz doğrudan veritabanına veya yapay zeka sunucusuna erişmez, her şey FastAPI üzerinden geçer (güvenlik ve sorumluluk ayrımı için).
- Ağır işler (OCR, embedding, e-posta gönderimi) backend'i **kilitlememesi** için Celery kuyruğuna devredilir. Bu sayede frontend her zaman hızlı yanıt alır, ağır iş arka planda yürür.
- Yapay zeka sunucusu (Ollama) ve veritabanı sunucusu, backend'in "yardımcı hizmetleri" gibi çalışır — birbirleriyle doğrudan konuşmazlar, her etkileşim FastAPI/Celery üzerinden orkestre edilir.

---

## 5. Teknoloji Yığını ve Seçim Gerekçeleri

Her teknoloji seçimi için "neden bu, neden bir alternatifi değil" mantığı aşağıda özetlenmiştir.

### 5.1 Frontend — Next.js + Tailwind + shadcn/ui

**Görevi:** İK yöneticisinin belge yüklediği, OCR çıktısını onayladığı, analitikleri gördüğü yönetim paneli.

**Neden seçildi:**
- Next.js, React tabanlı modern uygulamalar için endüstri standardı; sunucu taraflı render (SSR) ile hızlı ilk yükleme sağlar.
- Tailwind, hızlı ve tutarlı arayüz geliştirmeyi sağlar; özel CSS yazma ihtiyacını azaltır.
- shadcn/ui, hazır ama özelleştirilebilir bileşenler sunarak (buton, tablo, dialog vb.) geliştirme hızını artırır, "sıfırdan tasarım" yükünü azaltır.

**Alternatif olabilirdi:** Vue/Nuxt de tercih edilebilirdi; ancak React ekosisteminin genişliği ve iş ilanlarındaki yaygınlığı (CV değeri) Next.js'i öne çıkarıyor.

### 5.2 Backend API — Python (FastAPI)

**Görevi:** Tüm sistemin trafik yöneticisi; webhook'ları karşılar, yapay zeka servisleriyle konuşur, veritabanı işlemlerini yönetir.

**Neden seçildi:**
- **Asenkron mimari** (async/await) sayesinde, bir istek (örneğin bir e-posta webhook'u) beklerken diğer istekleri işlemeye devam edebilir — bu, aynı anda birçok e-postanın geldiği bir sistemde kritik.
- Python ekosistemi, yapay zeka kütüphaneleriyle (Ollama client, LangGraph, embedding işlemleri) doğal şekilde entegre olur.
- Otomatik API dokümantasyonu (Swagger/OpenAPI) üretir, geliştirme ve test sürecini hızlandırır.

**Alternatif olabilirdi:** Node.js/Express de asenkron çalışabilir, ancak yapay zeka/ML kütüphaneleriyle entegrasyon Python'da çok daha doğal ve az sürtünmelidir.

### 5.3 Asenkron Görev Kuyruğu — Celery + Redis

**Görevi:** OCR işleme, embedding oluşturma, e-posta gönderimi gibi zaman alan işleri arka plana atıp, ana API'nin hızlı ve duyarlı kalmasını sağlamak.

**Neden seçildi:**
- Bir kullanıcı belge yüklediğinde, OCR işlemi birkaç saniye sürebilir. Bu işlemi API isteğinin içinde senkron yaparsak, kullanıcı sayfada "yükleniyor" ekranında beklemek zorunda kalır ve sunucu kaynakları bloke olur.
- Celery, bu tür işleri bir **kuyruğa** koyar, arka planda çalışan "worker" süreçleri bunları sırayla (veya paralel) işler. Redis burada hem kuyruk (broker) hem de hızlı ara bellek (cache) görevi görür.
- Bu mimari aynı zamanda **hata toleransı** sağlar: bir OCR işlemi başarısız olursa, tekrar denenebilir; kullanıcı deneyimi kesintiye uğramaz.

**Not (performans tartışmasından):** Bu proje özelinde işler zaten iki kategoriye ayrılıyor — *seyrek ve ağır* (belge OCR onayı, ayda birkaç kez) ile *sık ama e-posta hızında yeterli* (gelen soru → cevap üretimi, dakikalar içinde cevap normal kabul edilir). Celery+Redis, tam olarak bu "hemen değil ama güvenilir sırayla" senaryosu için tasarlanmıştır — e-posta kanalının doğal gecikme toleransıyla mükemmel örtüşür.

### 5.4 Veritabanı + Vektör Arama — PostgreSQL + pgvector

**Görevi:** Hem klasik ilişkisel veriyi (şirketler, kullanıcılar, e-posta geçmişi) hem de yapay zeka için gerekli vektör (embedding) verisini tek bir veritabanında tutmak.

**Neden seçildi:**
- Ayrı bir vektör veritabanı (Qdrant, Milvus, Pinecone gibi) kurmak, ek altyapı, ek entegrasyon ve ek işletim yükü demektir.
- `pgvector`, PostgreSQL'e vektör arama yeteneği ekleyen bir eklenti. Şirket başına doküman hacmi (onlarca-yüzlerce politika belgesi) göz önüne alındığında, bu ölçekte pgvector performans olarak fazlasıyla yeterlidir.
- Tek veritabanı = tek yedekleme stratejisi, tek bakım süreci, daha az operasyonel karmaşıklık.

**Ne zaman yetersiz kalır:** Eğer sistem gerçekten büyür ve milyonlarca vektör/çok yüksek sorgu trafiği olursa, o zaman özel bir vektör veritabanına geçmek gerekebilir. Bu projenin ölçeğinde bu bir sorun değildir.

### 5.5 RAG Orkestrasyonu — LangGraph

**Görevi:** "Gelen soru → vektör arama → skor yeterli mi? → cevap üret ya da insana yönlendir" gibi **dallanan, durum tabanlı** mantığı yönetmek.

**Neden seçildi:**
- Bu iş akışı basit bir "sırayla çalıştır" zinciri değil; **koşullu dallanma** (if-else mantığı ama yapay zeka ajanı seviyesinde) içeriyor: skor yüksekse bir yola, düşükse başka bir yola gidiyor.
- LangGraph, bu tür akışları bir **durum makinesi (state machine)** olarak modellemeyi sağlar — hangi adımın hangi koşulda tetikleneceği açıkça tanımlanır, bu da hem kodun okunabilirliğini hem de hata ayıklamayı kolaylaştırır.
- Konuşma hafızasını (thread memory) akışın bir parçası olarak doğal şekilde taşıyabilir.

### 5.6 E-posta Altyapısı — Postmark / SendGrid Inbound Parse

**Görevi:** Çalışanın gönderdiği e-postayı yakalayıp sisteme JSON formatında iletmek, sistemin ürettiği cevabı da e-posta olarak göndermek.

**Neden seçildi:**
- E-posta protokolünü (SMTP, MIME ayrıştırma, spam/güvenlik başlıkları) sıfırdan yönetmek gereksiz bir mühendislik yükü. Bu servisler, gelen e-postayı doğrudan bir webhook'a (HTTP POST + JSON) çevirir.
- Kanıtlanmış, iyi dokümante edilmiş, yaygın kullanılan servisler.

**Dikkat edilmesi gereken nokta:** Bu servisler yurt dışı (genellikle ABD) merkezli çalışır. Yani "hiçbir veri dışarı çıkmıyor" iddiası sadece yapay zeka işlemleri (OCR/LLM/embedding) için geçerlidir — e-postanın kendisi zaten bu servislerden geçer. Gerçek bir ürün senaryosunda bu nokta müşteriye şeffaf şekilde anlatılmalı ya da hassas müşteriler için kurumun kendi mail sunucusu üzerinden IMAP polling gibi alternatif bir entegrasyon sunulmalıdır.

---

## 6. Yapay Zeka Model Stratejisi

### 6.1 Neden Lokal Model (Ollama) Kullanılıyor?

- **Veri gizliliği:** İK belgeleri ve e-posta içerikleri hassas kişisel veridir. Bu veriyi OpenAI/Anthropic gibi üçüncü parti bulut API'lerine göndermek yerine, şirketin kendi sunucusunda (veya SaaS sağlayıcısının kontrollü altyapısında) işlemek gizlilik açısından daha güçlü bir konumdur.
- **Maliyet yapısı:** Bulut API'leri token başına ücretlendirilir — kullanım arttıkça maliyet doğrusal artar. Lokal model, **değişken token maliyeti yerine sabit altyapı maliyeti** (GPU sunucusu) anlamına gelir. Düşük-orta trafikte bu daha öngörülebilir ve genellikle daha ucuzdur. *(Not: "sıfır maliyet" değildir — GPU sunucusu kurmak/kiralamak bir maliyettir, ama modelin kendisi ücretsiz ve token başına ödeme yoktur.)*

### 6.2 Seçilen Modeller ve Gerekçeleri

| Görev | Model | Seçim Gerekçesi |
|---|---|---|
| **Görsel OCR / Belge Anlama** | `qwen3-vl` (Ollama) | OCR desteği 32 dile genişletilmiş (önceki nesle göre 10'dan artmış), düşük ışık/bulanık/eğik görsellerde daha dayanıklı, uzun doküman yapısını (başlık, tablo) daha iyi koruyor. Bu proje özelinde telefonla çekilmiş, ideal olmayan koşullarda fotoğraflanmış belgeleri okuyacağı için önemli. |
| **Metin Üretimi (LLM)** | `qwen3.5` (Ollama) | Genel amaçlı, güncel bir dil modeli; e-posta yanıtı gibi doğal, kurumsal tonlu metin üretimi için yeterli kapasitede. Aynı model ailesinden (Qwen) olması, VL ve embedding modelleriyle tutarlı bir davranış/versiyon uyumu sağlıyor. |
| **Embedding (Vektörleştirme)** | `qwen3-embedding` (Ollama) | Metin gömme için özel eğitilmiş, 100'den fazla dil desteği var (Türkçe dahil çok dilli senaryolar için güçlü). Aynı model ailesinden olması entegrasyon ve bakım kolaylığı sağlıyor. |

**Neden aynı model ailesi (Qwen) tercih edildi?** Farklı sağlayıcılardan (örneğin bir OCR modeli + başka firmadan bir LLM + üçüncü firmadan embedding) modelleri bir araya getirmek, her birinin farklı davranış biçimini, farklı prompt formatını ve farklı güncelleme takvimini yönetmeyi gerektirir. Tek aile içinde kalmak bu karmaşıklığı azaltır.

**Lisans notu:** Qwen model ailesi Apache 2.0 lisanslıdır — ticari kullanımda (SaaS senaryosunda) lisans engeli yoktur.

### 6.3 Hangi Model Ne Zaman "Yük" Oluşturur? (Performans Tartışması)

Bu proje tasarlanırken en çok tartışılan nokta, üç modelin aynı GPU üzerinde çalışmasının performansı nasıl etkileyeceğiydi. Netleştirilen sonuç şu:

1. **OCR (qwen3-vl):** Sadece belge onay aşamasında, **seyrek** çalışır (şirket kuralları sık değişmez). Hatta mesai saatleri dışında toplu olarak işlenebilir. Gerçek zamanlı bir baskı oluşturmaz.
2. **Embedding (qwen3-embedding):** İki noktada çalışır — (a) doküman onaylandığında (seyrek), (b) her gelen e-postanın sorgu metnini vektörleştirmek için (her mailde bir kez). İkinci kullanım sık olsa da, embedding tek bir ileri geçiş (forward pass) işlemidir — kelime kelime metin üretmez, bu yüzden çok hızlıdır ve gerçek bir darboğaz oluşturmaz.
3. **LLM (qwen3.5):** Asıl "ağır" adım budur, çünkü cevap metni **token token** (kelime kelime) üretilir ve bu, embedding'e göre kat kat daha fazla işlem gerektirir.

**Neden bu bir sorun değil (bu proje ölçeğinde):** Sistemin kanalı **e-posta**dır. Bir chat arayüzünde kullanıcı 1-2 saniyede yanıt bekler; e-postada birkaç dakikalık gecikme tamamen normaldir ve kullanıcı tarafından fark edilmez. Celery kuyruğu zaten bu "hemen değil ama sırayla, güvenilir işlensin" mantığı için var. Yani mimari, bu potansiyel sorunu **kanal seçimi (e-posta) + kuyruk mimarisi (Celery)** kombinasyonuyla organik olarak çözmüş durumda.

**Bu ne zaman gerçek bir sorun haline gelir:** Sistem gerçekten çok sayıda şirket ve çok yüksek eşzamanlı e-posta trafiğiyle üretime çıkarsa (örn. binlerce çalışanı olan onlarca şirket aynı anda soru soruyorsa), tek GPU/tek Ollama sunucusu darboğaz oluşturabilir. Bu noktada yapılacaklar: birden fazla GPU worker'ı yatay ölçeklendirmek, model boyutunu (parametre sayısını) donanıma göre ayarlamak, veya LLM çağrılarını önceliklendirme/kuyruklama stratejisiyle yönetmek. **Bu projenin mevcut kapsamında bu bir öncelik değildir**, ama farkındalık olarak not edilmiştir.

---

## 7. Sistem Akışı: 5 Operasyonel Aşama

### Aşama 1: Doküman Dijitalleştirme ve İnsan Onayı (OCR & Human-in-the-Loop)

1. İK personeli, kural kağıdının fotoğrafını panelden yükler.
2. İstek Celery worker'ına devredilir, worker görseli `qwen3-vl` modeline gönderir.
3. Model, görseldeki başlıkları, paragrafları ve tabloları tanıyarak temiz bir Markdown çıktısı üretir.
4. **Kritik kontrol noktası:** Ekranda solda orijinal fotoğraf, sağda OCR çıktısı yan yana gösterilir. İK personeli karşılaştırıp onaylamadan içerik sisteme kalıcı olarak kaydedilmez.

*Neden insan onayı zorunlu?* Çünkü bir OCR hatası (örneğin bir yüzde işaretinin yanlış okunması) doğrudan çalışana yanlış, hukuki sonucu olan bir bilgi olarak gidebilir. Bu, sistemin en kritik güvenlik katmanıdır.

### Aşama 2: Vektörleştirme ve Şirket Bazlı İndeksleme (RAG Ingestion & Multi-Tenancy)

1. Onaylanan Markdown metni, başlık hiyerarşisine göre mantıksal parçalara (chunk) bölünür; tablo yapıları korunur.
2. Her parça `qwen3-embedding` ile vektöre dönüştürülür.
3. Vektörler, `company_id` etiketiyle birlikte PostgreSQL (`pgvector`) veritabanına kaydedilir.

*Neden `company_id` etiketi?* Bu, çok kiracılı (multi-tenant) sistemin temel taşı — A şirketinin çalışanı arama yaptığında sadece A şirketinin verileri içinde arama yapılmasını garanti eder (detay için Bölüm 9'a bakınız).

### Aşama 3: E-posta Yakalama ve Konuşma Hafızası (Inbound Mail & Thread Memory)

1. Çalışan `ik@sirket.com` adresine soru gönderir.
2. Postmark/SendGrid Inbound Webhook, mesajı JSON'a çevirip FastAPI'ye iletir.
3. Sistem, e-postanın `Message-ID`, `In-Reply-To`, `References` başlıklarını okur.
4. Eğer bu mesaj eski bir konuşmanın devamıysa, o thread'e ait geçmiş yazışmalar veritabanından çekilir.

*Neden thread hafızası önemli?* Çalışan "Peki ya cuma günleri?" diye takip sorusu sorduğunda, sistem bir önceki mesajda "uzaktan çalışma"dan bahsedildiğini hatırlamalı — aksi halde bağlamsız, anlamsız cevaplar üretir.

### Aşama 4: Karar Mekanizması, RAG Arama ve İnsana Yönlendirme (LangGraph Ajanı)

1. Gelen soru + e-posta geçmişi birleştirilip vektör araması yapılır.
2. **Güven eşiği (confidence threshold):** Benzerlik skoru eşik değerin üzerindeyse, LangGraph ajanı dokümana dayanarak `qwen3.5` ile nazik bir e-posta taslağı üretir.
3. **İnsana yönlendirme (escalation):** Skor düşükse veya dokümanda bilgi yoksa, sistem **uydurma cevap üretmez**. Çalışana "bu konuda net bilgi bulunamadı, talebiniz İK'ya iletildi" maili gider, gerçek İK personeline bildirim düşer.

*Bilinen sınırlama:* Benzerlik skoru yüksek olması, bulunan metnin sorunun **tam ve doğru cevabı** olduğu anlamına gelmez — sadece "alakalı" olduğunu gösterir. Gerçek bir üründe bu noktaya ek bir doğrulama katmanı (reranker veya "üretilen cevap gerçekten kaynakta var mı" kontrolü) eklenmesi önerilir (Bölüm 11'de detaylandırılmıştır).

### Aşama 5: E-posta Yanıtı ve Analiz (Outbound Mail & Analytics)

1. Hazırlanan cevap, Postmark/SendGrid üzerinden çalışana gönderilir.
2. Konuşma, veritabanına thread geçmişi olarak işlenir.
3. İK panelinde en sık sorulan sorular ve dokümantasyonda eksik kalan (İK'ya yönlendirilen) konular analitik olarak gösterilir — bu da İK'ya "hangi politikayı netleştirmemiz gerekiyor" içgörüsü sağlar.

---

## 8. Detaylı Veri Akış Şemaları

### Akış A: Doküman Dijitalleştirme (Ingestion)

```text
[ İK Personeli ]
       │  1. Görsel / PDF Yükler
       ▼
[ Next.js Frontend ]
       │  2. POST /api/v1/documents/upload
       ▼
[ FastAPI Backend ]
       │  3. Dosyayı kaydeder, Celery'ye görev atar
       ▼
[ Celery Worker ]
       │  4. Görseli Ollama API'ye gönderir
       ▼
[ Ollama (qwen3-vl) ]
       │  5. Markdown formatında metin/tablo çıktısı döner
       ▼
[ Celery Worker ] ──(6. Durum Günceller)──► [ PostgreSQL ] (Status: 'pending_approval')
       │
       │  7. UI'a bildirim gider
       ▼
[ Next.js Frontend ] ──(İK kontrol eder)──► [ 'Onayla' Butonu ]
       │
       │  8. POST /api/v1/documents/approve
       ▼
[ FastAPI Backend ]
       │  9. Chunking + qwen3-embedding ile vektörleştirme
       ▼
[ PostgreSQL (pgvector) ] ──(10. Vektör & Chunk Saklama)
```

### Akış B: E-posta Yakalama, RAG Karar Mekanizması ve Cevaplama

```text
[ Çalışan ]
    │  1. E-posta atar (ik@sirket.com)
    ▼
[ SendGrid / Postmark ]
    │  2. Inbound Webhook (JSON: Gönderen, Konu, Gövde, Başlıklar)
    ▼
[ FastAPI Backend ]
    │  3. Message-ID & In-Reply-To Başlıklarını Okur
    ▼
[ PostgreSQL DB ] ──(4. Eski Thread Geçmişini Çek)──► [ FastAPI ]
                                                             │
                                          5. Görevi Celery'ye At
                                                             ▼
                                                     [ Celery Worker ]
                                                             │
                                          6. Soru Vektörleştirilir (qwen3-embedding)
                                                             ▼
                                                   [ pgvector DB ]
                                                             │
                                           7. Cosine Similarity Search
                                              (WHERE company_id = X)
                                                             ▼
                                                     [ LangGraph Ajanı ]
                                                             │
                                   ┌─────────────────────────┴─────────────────────────┐
                                   ▼                                                   ▼
                      [ Benzerlik Skoru >= Eşik ]                         [ Benzerlik Skoru < Eşik ]
                                   │                                                   │
                                   ▼                                                   ▼
                         [ Ollama (qwen3.5) ]                             [ İK'ya Bildirim Düşer ]
                         (RAG + Hafıza Promptu)                          (Escalation Tetiklenir)
                                   │                                                   │
                                   ▼                                                   ▼
                      [ Cevap Maili Hazırlanır ]                          [ "Talebiniz İK'ya İletildi" ]
                                   │                                                   │
                                   └─────────────────────────┬─────────────────────────┘
                                                             │
                                                             ▼
                                                    [ SendGrid API ]
                                                             │
                                                             ▼
                                                        [ Çalışan ]
```

---

## 9. Güvenlik ve Çok Kiracılı (Multi-Tenant) İzolasyon

- **Uygulama seviyesi izolasyon:** Her veritabanı kaydı bir `company_id` etiketi taşır; her sorgu bu etiketle filtrelenir.
- **Önerilen ek katman — Row Level Security (RLS):** Sadece uygulama kodundaki `WHERE company_id = X` filtresine güvenmek risklidir; bir geliştiricinin bu satırı unutması, şirketler arası veri sızıntısına yol açabilir. PostgreSQL'in RLS özelliği, bu kuralı **veritabanı seviyesinde** zorunlu kılarak ikinci bir güvenlik katmanı (defense in depth) sağlar.
- **Sıfır dış veri transferi (yapay zeka için):** OCR, embedding ve LLM işlemleri tamamen lokal Ollama sunucusunda gerçekleştiği için bu veriler OpenAI/Anthropic gibi üçüncü parti yapay zeka sağlayıcılarına gönderilmez. *(Not: E-posta altyapısı için Bölüm 5.6'daki uyarı geçerlidir.)*

---

## 10. Performans ve Ölçeklenebilirlik Değerlendirmesi

Bu bölüm, Bölüm 6.3'te özetlenen tartışmanın sonucudur:

- **Mevcut kapsamda (portföy/demo/az sayıda şirket):** Tek GPU üzerinde çalışan Ollama sunucusu yeterlidir. OCR ve embedding işlemleri seyrek/hafif olduğu için, asıl yük LLM cevap üretimindedir — ve bu da e-posta kanalının doğal gecikme toleransı sayesinde sorun oluşturmaz.
- **Gerçek üretim senaryosunda (çok sayıda şirket, yüksek eşzamanlı trafik):** GPU darboğazı oluşabilir. Bu durumda: (a) birden fazla GPU worker'ı ile yatay ölçekleme, (b) model boyutunu donanıma göre optimize etme, (c) LLM çağrıları için önceliklendirme/kuyruklama stratejisi eklenmesi gerekir. **Bu, mevcut proje kapsamının dışındadır ama gelecekteki bir yol haritası maddesi olarak not edilmiştir.**
- **Maliyet çerçevesi:** Lokal model kullanmak "sıfır maliyet" değildir — GPU sunucusu (kendi donanımı veya kiralık bulut GPU'su) bir sabit/işletim maliyetidir. Ancak token başına değişken ücret olmadığı için, öngörülebilir ve genellikle API tabanlı çözümlerden daha ekonomik bir maliyet yapısı sunar.

---

## 11. Bilinen Sınırlamalar ve Gerçek Ürüne Dönüşürse Yapılması Gerekenler

Bu bölüm, projenin bir CV/portföy projesi olarak tasarlandığının bilinçli bir sonucudur — aşağıdaki noktalar **şu an için çözülmemiştir** ama gerçek bir ticari ürüne dönüşme senaryosunda ele alınması gereken konulardır:

1. **KVKK Uyumluluğu:** Sistem çalışan kişisel verisi işlediği için Türkiye'de KVKK kapsamına girer. Gerçek bir üründe, her müşteri şirketle veri işleyen/veri sorumlusu ilişkisini netleştiren bir sözleşme ve gerekirse VERBIS kaydı süreci gerekir.
2. **Retrieval Güvenilirliği:** Cosine similarity skoru tek başına "doğru cevap" garantisi vermez. Gerçek üründe bir **reranker modeli** (ikinci aşama, daha hassas bir alaka skorlaması) veya üretilen cevabın kaynak metinde gerçekten var olup olmadığını kontrol eden bir "groundedness check" adımı eklenmesi önerilir.
3. **Onboarding Sürtünmesi:** E-posta yakalama (MX kaydı yönlendirme / inbound parse kurulumu), kurumsal müşteri tarafında BT/güvenlik onayı gerektiren, satış sürecini yavaşlatan bir adımdır. Gerçek üründe bu süreç için daha net bir kurulum rehberi/otomasyonu gerekir.
4. **Üçüncü Parti E-posta Servisi Şeffaflığı:** "Veri dışarı çıkmıyor" iddiası sadece yapay zeka işlemleri için geçerlidir; e-posta içeriği Postmark/SendGrid gibi servislerden geçer. Bu netleştirilmeli veya hassas müşteriler için alternatif (kurumun kendi mail sunucusu) sunulmalıdır.
5. **Kurumsal Güven ve Sertifikasyon:** İK verisi çok hassas olduğu için kurumsal müşteriler genellikle güvenlik denetimi/sertifikasyon (örn. ISO 27001, SOC 2 benzeri) bekler — bu, tek kişilik bir projeyle kısa vadede karşılanabilecek bir gereklilik değildir.
6. **Ekip İhtiyacı:** Bu maddelerin tamamını (satış, hukuki uyum, güvenlik sertifikasyonu, destek) çözüp gerçek bir SaaS ürünü haline getirmek, tek başına yapılabilecek bir iş değildir — bu başlı başına bir ekip/şirket işidir. Bu proje, o vizyonun **teknik çekirdeğinin** bir kanıtı (proof of concept) olarak tasarlanmıştır.

---

## 12. Proje Kapsamı: MVP ve Uzun Vadeli Vizyon

**Bu projede hedeflenen (Faz 1 — Portföy/Demo Kapsamı):**

- Tek bir örnek şirket üzerinden uçtan uca çalışan tam akış: belge yükleme → OCR → onay → vektörleştirme → e-posta ile soru → RAG cevabı veya yönlendirme.
- Yukarıda anlatılan tüm teknik bileşenlerin (FastAPI, Celery, PostgreSQL/pgvector, Ollama/Qwen modelleri, LangGraph, e-posta webhook) gerçek, çalışan bir entegrasyonu.
- Temel güvenlik önlemleri (multi-tenant filtreleme, human-in-the-loop onay).

**Kapsam dışı (Faz 2+ — Gerçek Ürün Vizyonu, şu an için sadece yol haritası):**

- Çoklu şirket ölçeklendirmesi ve GPU altyapı optimizasyonu.
- KVKK/hukuki uyum süreçleri.
- Faturalama, self-servis onboarding, müşteri destek sistemi.
- Reranker/groundedness doğrulama katmanı.
- Güvenlik sertifikasyonu süreçleri.

---

## 13. Sözlük

| Terim | Açıklama |
|---|---|
| **RAG (Retrieval-Augmented Generation)** | Yapay zekanın cevap üretmeden önce ilgili dokümanlardan bilgi "arayıp bulduğu" ve bu bilgiye dayanarak cevap ürettiği yöntem. Amaç, modelin bilgiyi uydurmasını (halüsinasyon) engellemek. |
| **Embedding (Vektörleştirme)** | Bir metni, anlamını temsil eden bir sayı dizisine (vektöre) dönüştürme işlemi. Benzer anlamlı metinler, vektör uzayında birbirine yakın konumlanır. |
| **Vektör Veritabanı** | Bu vektörleri saklayıp, "bu soruya en yakın anlamlı metin hangisi" sorgusunu hızlıca cevaplayabilen veritabanı türü (bu projede: PostgreSQL + pgvector). |
| **Webhook** | Bir sistemin, belirli bir olay gerçekleştiğinde (örn. "yeni e-posta geldi") otomatik olarak başka bir sisteme HTTP isteği göndermesi mekanizması. |
| **Multi-Tenancy (Çok Kiracılılık)** | Tek bir sistemin, birden fazla bağımsız müşteriye (şirkete) hizmet verirken, her birinin verisini birbirinden tamamen izole tutması. |
| **Human-in-the-Loop** | Yapay zeka çıktısının otomatik olarak kullanılmadan önce bir insan tarafından kontrol edilip onaylandığı süreç tasarımı. |
| **Thread Memory (Konuşma Hafızası)** | Sistemin, bir e-posta yazışmasının önceki mesajlarını hatırlayıp yeni mesajı bu bağlamda değerlendirmesi. |
| **Confidence Threshold (Güven Eşiği)** | Vektör aramasında bulunan sonucun "yeterince alakalı" sayılması için gereken minimum benzerlik skoru. |
| **Escalation (Yönlendirme)** | Sistemin, kendinden emin olmadığı bir durumda soruyu otomatik cevaplamak yerine bir insana devretmesi. |
| **Ollama** | Büyük dil modellerini kendi bilgisayarınızda/sunucunuzda (lokal) çalıştırmanızı sağlayan açık kaynaklı araç. |
| **Row Level Security (RLS)** | Veritabanı seviyesinde, hangi kullanıcının hangi satırlara erişebileceğini kısıtlayan güvenlik mekanizması. |

---

*Bu doküman, proje geliştirme sürecinde alınan kararları ve gerekçelerini kayıt altına almak amacıyla hazırlanmıştır. İlerleyen aşamalarda yapılan değişiklikler bu dokümana yansıtılmalıdır.*