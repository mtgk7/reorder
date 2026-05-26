# 🔄 ReOrder — Trendyol Müşteri Retention & Analiz Platformu

Trendyol'da satış yapan mağazaların müşteri sadakatini, geri dönüş oranlarını ve ömür boyu değerini (LTV) otomatik analiz eden **multi-tenant SaaS** uygulaması.

---

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Python 3.10+

### Kurulum

```bash
cd C:\Users\gokbu\Documents\reorder
python -m pip install -r requirements.txt
```

### Çalıştırma

```bash
python -m streamlit run app.py
```

Tarayıcıda `http://localhost:8501` açılır.

---

## 📁 Dosya Yapısı

```
reorder/
├── src/
│   ├── __init__.py
│   ├── auth.py           — bcrypt kayıt/giriş, şifre değiştirme, multi-tenant
│   ├── database.py       — SQLite şeması (users, orders, user_settings), init_db
│   ├── parser.py         — Trendyol Excel/CSV otomatik sütun tanıma + örnek veri üretici
│   ├── analytics.py      — Cohort retention, LTV, RFM segmentasyon, aylık trend
│   ├── trendyol_api.py   — Trendyol Satıcı API istemcisi + credential yönetimi
│   └── report.py         — 3 sayfalık A4 PDF rapor üreteci (fpdf2 + matplotlib)
├── app.py                — Streamlit Web Arayüzü (5 sayfa)
├── data/
│   └── reorder.db        — SQLite veritabanı (otomatik oluşur)
├── requirements.txt
└── README.md
```

---

## ✅ Tamamlanan Özellikler

### v1.0 — Temel Altyapı

| Özellik | Açıklama |
|---|---|
| **Multi-tenant Auth** | Kayıt, giriş, bcrypt şifreleme. Her mağaza kendi verisini görür |
| **SQLite Veritabanı** | `users`, `orders`, `user_settings` tabloları, WAL modu, indeksler |
| **Excel/CSV Import** | Trendyol sipariş raporlarını otomatik sütun eşleştirmeyle içe aktarır |
| **Örnek Veri Üretici** | 30–300 müşteri, 12 aylık sentetik sipariş (demo amaçlı) |
| **Streamlit UI** | 5 sayfalı tam arayüz, turuncu (#F27A1A) renk teması |

### v1.0 — Analitik Motoru

| Özellik | Açıklama |
|---|---|
| **Dashboard** | 7 KPI kartı · aylık gelir trend grafiği · yeni vs geri dönen müşteri |
| **Cohort Analizi** | Aylık cohort retention ısı haritası (Ay 0–11) |
| **LTV Analizi** | Dağılım histogramı · top 10 müşteri · Pareto (80/20) analizi |
| **Retention Trend** | Aylık retention oranı çizgi grafiği |
| **RFM Segmentasyon** | 6 segment · pasta + bar grafik · 100 müşteri listesi |

### v2.0 — Gelişmiş Özellikler

| Özellik | Açıklama |
|---|---|
| **PDF Rapor** | Tek tıkla 3 sayfalık A4 PDF: metrikler + trend grafiği + cohort matrisi (renkli) + segmentler + top 10 LTV |
| **Trendyol API** | Satıcı ID + API key ile siparişleri otomatik çek · son 7/30/90 gün preset · özel tarih aralığı · senkronizasyon geçmişi |
| **Ayarlar** | Mağaza adı güncelleme · şifre değiştirme · API credential yönetimi |

---

## 📊 Analitik Metodoloji

### Cohort Retention
Müşteriler **ilk alışveriş yaptıkları aya** göre gruplandırılır (cohort).
Her cohort için sonraki aylarda kaç müşterinin tekrar alışveriş yaptığı yüzdesel olarak gösterilir.

```
Retention % = (Ayda aktif eski müşteri) / (Cohort büyüklüğü) × 100
```

### LTV (Lifetime Value)
Müşteri başına toplam harcama. Ortalama, dağılım ve en yüksek değer gösterilir.

### RFM Segmentleri

| Segment | Kriter |
|---|---|
| 🟢 Sadık Müşteri | 4+ sipariş, son 90 gün aktif |
| 🔵 Gelişen Müşteri | 2–3 sipariş, son 90 gün aktif |
| 🟡 Yeni Müşteri | 1 sipariş, son 90 gün |
| 🔴 Risk Altında | 2–3 sipariş, 90+ gün sessiz |
| ⚫ Tek Alışveriş | 1 sipariş, 90+ gün sessiz |
| 🔘 Kaybolma Riski | 4+ sipariş ama 90+ gün sessiz |

---

## 🔌 Trendyol API Entegrasyonu

**Nasıl yapılandırılır:**
1. Trendyol Satıcı Paneli → **Entegrasyonlar → API Entegrasyonları**
2. **Satıcı ID**, **API Key** ve **API Secret** bilgilerini kopyalayın
3. Uygulamada **Ayarlar → Trendyol API** bölümüne girin ve kaydedin
4. **Veri Yükle → Trendyol API** sekmesinden senkronizasyonu başlatın

**Desteklenen işlemler (`src/trendyol_api.py`):**

```python
client = TrendyolClient(seller_id, api_key, api_secret)
client.get_orders(start_date, end_date)       # Sipariş listesi
client.get_all_orders(start_date, end_date)   # Sayfalı tam çekme
client.test_connection()                       # Bağlantı testi
```

API Dokümantasyonu: https://developers.trendyol.com/tr/docs/category/sipariş

---

## 📄 PDF Rapor

Dashboard → **"📄 PDF Raporu Hazırla"** butonuna tıklayın.

**Rapor içeriği (3 sayfa):**
- **Sayfa 1** — 7 KPI kartı + aylık gelir/sipariş çift eksenli grafik + aylık özet tablosu
- **Sayfa 2** — Cohort retention matrisi (yeşil ≥%80 · sarı ≥%50 · turuncu ≥%20 · kırmızı <%20)
- **Sayfa 3** — RFM segment dağılımı + gelir katkısı + top 10 LTV müşteri listesi

---

## 🗃️ Veritabanı Şeması

```sql
-- Kullanıcılar
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    store_name    TEXT NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Siparişler
CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL,
    order_number        TEXT,
    customer_identifier TEXT NOT NULL,
    order_date          DATE NOT NULL,
    total_amount        REAL NOT NULL DEFAULT 0,
    status              TEXT,
    product_name        TEXT,
    quantity            INTEGER DEFAULT 1,
    import_batch        TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, order_number, customer_identifier)
);

-- Kullanıcı Ayarları (API credentials + senkronizasyon geçmişi)
CREATE TABLE user_settings (
    user_id             INTEGER PRIMARY KEY,
    trendyol_seller_id  TEXT,
    trendyol_api_key    TEXT,
    trendyol_api_secret TEXT,
    last_sync_at        DATETIME,
    last_sync_count     INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## 📦 Bağımlılıklar

```
streamlit>=1.35.0      # Web arayüzü
pandas>=2.0.0          # Veri işleme
openpyxl>=3.1.0        # Excel okuma
xlrd>=2.0.1            # Eski Excel formatları
bcrypt>=4.0.0          # Şifre hashleme
plotly>=5.18.0         # İnteraktif grafikler
python-dateutil>=2.8.0 # Tarih işlemleri
numpy>=1.24.0          # Sayısal hesaplamalar
fpdf2>=2.7.0           # PDF üretimi
matplotlib>=3.7.0      # PDF içi grafikler
```

---

## 🔜 Planlanan Özellikler (v3.0)

- [ ] **E-posta kampanyaları** — "Risk Altında" / "Kaybolma Riski" segmentine otomatik mesaj (SendGrid/SMTP)
- [ ] **Deployment** — Streamlit Cloud veya Vercel'e yayınlama
- [ ] **PostgreSQL geçişi** — Üretim ortamı için SQLite → PostgreSQL
- [ ] **Çoklu mağaza** — Tek hesapla birden fazla mağaza yönetimi
- [ ] **Webhook** — Trendyol sipariş bildirimleri ile gerçek zamanlı senkronizasyon

---

## 🛠️ Geliştirme Notları

```bash
# Sanal ortam (önerilen)
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Uygulamayı başlat
python -m streamlit run app.py

# Veritabanını sıfırla (dikkat: tüm veri silinir)
python -c "from src.database import delete_all_orders; ..."
```

**Bilinen durumlar (sorun değil):**
- Plotly `_hoverlayer` TypeError → sayfa geçişinde grafik unmount race condition (Streamlit/Plotly)
- "Password not in form" → Streamlit'in kendi HTML çıktısı

---

*Claude Code ile oluşturuldu — 2026*
