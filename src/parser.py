"""
parser.py — Trendyol Excel/CSV sipariş raporu okuyucu ve DB'ye aktarıcı.
Farklı Trendyol export formatlarını otomatik tanır.
"""
import re
import io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.database import get_connection

# ─────────────────────────────────────────────────────────────────────────────
# Sütun adı eşleştirme tablosu
# ─────────────────────────────────────────────────────────────────────────────
COLUMN_MAP: dict[str, list[str]] = {
    "order_number": [
        "Sipariş Numarası", "Sipariş No", "Siparis No",
        "Order No", "Order Number", "orderNumber", "Paket No",
    ],
    "customer_identifier": [
        "Alıcı Adı Soyadı", "Alici Adi Soyadi", "Müşteri Adı",
        "Müşteri Adı Soyadı", "Alıcı", "Musteri", "Customer Name",
        "Buyer Name", "Ad Soyad",
    ],
    "order_date": [
        "Sipariş Tarihi", "Sipariş Oluşturma Tarihi", "Siparis Tarihi",
        "Tarih", "Order Date", "Date", "Oluşturma Tarihi",
    ],
    "total_amount": [
        "Toplam Tutar", "Tutar", "Satış Fiyatı", "Fiyat",
        "Net Tutar", "Toplam", "Total", "Amount",
        "Toplam Satış Tutarı", "İndirimli Fiyat", "Satış Tutarı",
    ],
    "product_name": [
        "Ürün Adı", "Ürün", "Urun Adi", "Product Name", "Ürün İsmi",
    ],
    "quantity": [
        "Adet", "Miktar", "Quantity", "Qty",
    ],
    "status": [
        "Durum", "Sipariş Durumu", "Status", "İptal/İade Durumu",
    ],
    "city": [
        "İl", "Şehir", "Teslimat İli", "Alıcı İli", "Delivery City",
        "City", "İl/İlçe", "Teslimat Şehri", "Şehir/İlçe",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _detect_col(df: pd.DataFrame, field: str) -> str | None:
    """DataFrame'de bir alana karşılık gelen sütunu bulur."""
    candidates = COLUMN_MAP.get(field, [])
    cols_lower = {c.lower(): c for c in df.columns}

    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in cols_lower:
            return cols_lower[name.lower()]
    return None


def _parse_amount(value) -> float:
    """Türkçe para formatını (1.234,56 TL) float'a çevirir."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d,\.]", "", str(value).strip())
    if "," in s and "." in s:
        # 1.234,56 → 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


_DATE_FMTS = [
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]


def _parse_date(value) -> tuple[str | None, int | None]:
    """(YYYY-MM-DD, saat_0_23) tuple döndürür. Saat yoksa None."""
    if pd.isna(value):
        return None, None
    if hasattr(value, "strftime"):
        hour = value.hour if hasattr(value, "hour") else None
        return value.strftime("%Y-%m-%d"), hour
    s = str(value).strip()
    for fmt in _DATE_FMTS:
        try:
            dt = datetime.strptime(s[:len(fmt)], fmt)
            date_str = dt.strftime("%Y-%m-%d")
            hour = dt.hour if "%H" in fmt else None
            return date_str, hour
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.strftime("%Y-%m-%d"), dt.hour
    except Exception:
        return None, None


def _read_raw(file) -> pd.DataFrame:
    """Dosyayı ham DataFrame olarak okur (CSV veya Excel)."""
    name = getattr(file, "name", str(file))
    ext = Path(name).suffix.lower()

    if ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "cp1254", "latin1"):
            for sep in (";", ",", "\t"):
                try:
                    if hasattr(file, "seek"):
                        file.seek(0)
                    df = pd.read_csv(file, encoding=enc, sep=sep, dtype=str)
                    if df.shape[1] >= 3:
                        return df
                except Exception:
                    pass
        raise ValueError("CSV dosyası okunamadı. Farklı bir kodlama veya ayraç deneyin.")

    if ext in (".xlsx", ".xls"):
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        for header_row in (0, 1, 2):
            try:
                if hasattr(file, "seek"):
                    file.seek(0)
                df = pd.read_excel(file, header=header_row, engine=engine, dtype=str)
                if df.shape[1] >= 3 and not df.empty:
                    return df
            except Exception:
                pass
        raise ValueError("Excel dosyası okunamadı.")

    raise ValueError(f"Desteklenmeyen format: {ext}. Lütfen .xlsx veya .csv yükleyin.")


# ─────────────────────────────────────────────────────────────────────────────
# Ana parse fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def parse_trendyol_file(file) -> dict:
    """
    Trendyol sipariş dışa aktarma dosyasını parse eder.

    Dönüş sözlüğü::
        success  : bool
        data     : pd.DataFrame | None   — normalleştirilmiş sipariş tablosu
        col_map  : dict                  — tespit edilen sütun eşlemeleri
        errors   : list[str]
        warnings : list[str]
        row_count: int
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        raw = _read_raw(file)
    except ValueError as exc:
        return {"success": False, "data": None, "col_map": {}, "errors": [str(exc)], "warnings": []}

    raw.columns = [str(c).strip() for c in raw.columns]

    # Sütunları tespit et
    col_map = {field: _detect_col(raw, field) for field in COLUMN_MAP}
    col_map = {k: v for k, v in col_map.items() if v is not None}

    # Zorunlu sütun kontrolü
    required = ["customer_identifier", "order_date", "total_amount"]
    missing = [f for f in required if f not in col_map]
    if missing:
        labels = {"customer_identifier": "Müşteri Adı", "order_date": "Sipariş Tarihi", "total_amount": "Tutar"}
        miss_str = ", ".join(labels.get(f, f) for f in missing)
        avail = ", ".join(raw.columns.tolist()[:15])
        errors.append(
            f"Gerekli sütunlar bulunamadı: {miss_str}.\n"
            f"Dosyadaki sütunlar: {avail}"
        )
        return {"success": False, "data": None, "col_map": col_map, "errors": errors, "warnings": warnings}

    # Normalleştirilmiş tablo oluştur
    out = pd.DataFrame()
    out["customer_identifier"] = raw[col_map["customer_identifier"]].astype(str).str.strip()
    _parsed = raw[col_map["order_date"]].apply(_parse_date)
    out["order_date"] = _parsed.apply(lambda x: x[0])
    out["order_hour"] = _parsed.apply(lambda x: x[1])
    out["total_amount"] = raw[col_map["total_amount"]].apply(_parse_amount)

    if "order_number" in col_map:
        out["order_number"] = raw[col_map["order_number"]].astype(str).str.strip()
    else:
        out["order_number"] = [f"AUTO-{i}" for i in range(len(raw))]
        warnings.append("Sipariş numarası sütunu bulunamadı; otomatik numara atandı.")

    out["product_name"] = raw[col_map["product_name"]].astype(str).str.strip() if "product_name" in col_map else ""
    out["quantity"] = (
        pd.to_numeric(raw[col_map["quantity"]], errors="coerce").fillna(1).astype(int)
        if "quantity" in col_map else 1
    )
    out["status"] = raw[col_map["status"]].astype(str).str.strip() if "status" in col_map else "Teslim Edildi"
    out["city"] = raw[col_map["city"]].astype(str).str.strip() if "city" in col_map else ""

    # Temizlik
    before = len(out)
    out = out[out["order_date"].notna()]
    out = out[~out["customer_identifier"].isin(["", "nan", "NaN", "None"])]
    skipped = before - len(out)
    if skipped:
        warnings.append(f"{skipped} satır eksik/geçersiz veri nedeniyle atlandı.")

    if out.empty:
        errors.append("Dosyada geçerli sipariş verisi bulunamadı.")
        return {"success": False, "data": None, "col_map": col_map, "errors": errors, "warnings": warnings}

    return {
        "success": True,
        "data": out.reset_index(drop=True),
        "col_map": col_map,
        "errors": [],
        "warnings": warnings,
        "row_count": len(out),
    }


def import_to_db(
    df: pd.DataFrame,
    user_id: int,
    batch: str | None = None,
    store_id: int | None = None,
) -> dict:
    """
    Parse edilmiş sipariş DataFrame'ini veritabanına yazar.

    Dönüş:
        {'inserted': int, 'skipped': int, 'batch': str}
    """
    if batch is None:
        batch = datetime.now().strftime("%Y%m%d_%H%M%S")

    conn = get_connection()
    cur = conn.cursor()
    inserted = skipped = 0

    for row in df.itertuples(index=False):
        try:
            city_val = str(getattr(row, "city", "") or "")
            hour_val = getattr(row, "order_hour", None)
            if hour_val is not None:
                try:
                    hour_val = int(hour_val)
                except (ValueError, TypeError):
                    hour_val = None
            cur.execute(
                """
                INSERT INTO orders
                    (user_id, store_id, order_number, customer_identifier, order_date,
                     total_amount, status, product_name, quantity, import_batch,
                     city, order_hour)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT DO NOTHING
                """,
                (
                    user_id,
                    store_id,
                    str(row.order_number),
                    str(row.customer_identifier),
                    str(row.order_date),
                    float(row.total_amount),
                    str(row.status),
                    str(row.product_name),
                    int(row.quantity),
                    batch,
                    city_val,
                    hour_val,
                ),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    conn.commit()
    conn.close()
    return {"inserted": inserted, "skipped": skipped, "batch": batch}


# ─────────────────────────────────────────────────────────────────────────────
# Örnek veri üretici (test / demo amaçlı)
# ─────────────────────────────────────────────────────────────────────────────

STORE_PRODUCTS: dict[str, list[str]] = {
    "elektronik": [
        "Akıllı Telefon", "Laptop", "Tablet", "Kablosuz Kulaklık",
        "Şarj Aleti", "Powerbank", "Akıllı Saat", "Bluetooth Hoparlör",
        "Oyun Konsolu", "Fotoğraf Makinesi", "SSD Disk", "USB Hub",
    ],
    "giyim": [
        "Erkek Tişört", "Kadın Bluz", "Kot Pantolon", "Spor Ayakkabı",
        "Kışlık Mont", "Elbise", "Kazak", "Gömlek", "Şort",
        "Çanta", "Kemer", "Eşarp",
    ],
    "spor": [
        "Yoga Matı", "Dumbbell Set", "Protein Tozu", "Sporcu Çantası",
        "Bisiklet Kaskı", "Yüzücü Gözlüğü", "Tenis Raketi",
        "Fitness Eldiveni", "Atlama İpi", "Koşu Bandı", "Labut Set", "Ter Bandı",
    ],
    "ev": [
        "Kahve Makinesi", "Robot Süpürge", "Hava Fritözü", "Pasta Kalıbı",
        "Dekoratif Yastık", "Bambu Kesme Tahtası", "Çay Bardağı Seti",
        "Mum Seti", "Organizör Kutu", "Havlu Seti", "Koku Difüzörü", "Pişirme Seti",
    ],
    "default": [
        "Erkek Spor Ayakkabı", "Kadın Bot", "Çocuk Kabot", "Deri Cüzdan",
        "Laptop Çantası", "Bluetooth Kulaklık", "Akıllı Saat", "Güneş Gözlüğü",
        "Parfüm", "Saç Kurutma Makinesi", "Termos", "Yoga Matı",
    ],
}


def _detect_store_category(store_name: str) -> str:
    """Mağaza adından ürün kategorisi tespit eder."""
    name = store_name.lower()
    if any(k in name for k in ["elektro", "tech", "dijital", "bilişim"]):
        return "elektronik"
    if any(k in name for k in ["giyim", "tekstil", "moda", "fashion", "butik"]):
        return "giyim"
    if any(k in name for k in ["spor", "fitness", "sport"]):
        return "spor"
    if any(k in name for k in ["ev", "yaşam", "home", "dekor", "mutfak"]):
        return "ev"
    return "default"


def generate_sample_orders(
    n_customers: int = 120,
    seed: int = 42,
    products: list[str] | None = None,
    store_name: str = "",
) -> pd.DataFrame:
    """
    Gerçekçi Trendyol sipariş verisi simüle eder.
    Cohort analizi için 12 aylık veri üretir.
    store_name verilirse mağazaya uygun ürün listesi otomatik seçilir.
    """
    rng = np.random.default_rng(seed)
    names_first = [
        "Ahmet", "Mehmet", "Ali", "Mustafa", "Ömer", "İbrahim", "Hüseyin",
        "Ayşe", "Fatma", "Zeynep", "Elif", "Emine", "Hatice", "Merve",
        "Yusuf", "Hasan", "Murat", "Serkan", "Emre", "Burak",
        "Selin", "Derya", "Gamze", "Esra", "Gül", "Pınar",
    ]
    names_last = [
        "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Doğan", "Kılıç",
        "Arslan", "Taş", "Aydın", "Özdemir", "Koç", "Kurt", "Öztürk",
        "Erdoğan", "Aktaş", "Çetin", "Polat", "Korkmaz", "Güneş",
    ]
    if products is None:
        category = _detect_store_category(store_name)
        products = STORE_PRODUCTS[category]

    CITIES = [
        "İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana",
        "Konya", "Mersin", "Gaziantep", "Kocaeli", "Trabzon", "Diyarbakır",
        "Eskişehir", "Samsun", "Kayseri",
    ]
    CITY_WEIGHTS = [0.30, 0.15, 0.10, 0.07, 0.06, 0.05, 0.04, 0.04, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02, 0.01]
    # Saatlik ağırlıklar: 10-22 arası yoğun
    _hour_raw = [
        1, 1, 1, 1, 1, 1,   # 0-5 (gece)
        2, 3, 5, 8,          # 6-9 (sabah)
        12, 14, 13, 11,      # 10-13 (öğle)
        10, 10, 11, 13,      # 14-17 (öğleden sonra)
        15, 15, 13, 12,      # 18-21 (akşam)
        9, 5,                # 22-23 (gece)
    ]
    _hour_total = sum(_hour_raw)
    HOUR_WEIGHTS = [v / _hour_total for v in _hour_raw]

    customers = [
        f"{rng.choice(names_first)} {rng.choice(names_last)}"
        for _ in range(n_customers)
    ]

    base_date = datetime(2025, 5, 1)
    records = []

    for cust in customers:
        # İlk alışveriş: 0-11 ay önce (farklı cohort'lar)
        first_offset = int(rng.integers(0, 365))
        first_date = base_date + pd.Timedelta(days=-first_offset + 365)

        # Ortalama 1-4 sipariş
        n_orders = int(rng.choice([1, 1, 2, 2, 3, 4], p=[0.35, 0.20, 0.20, 0.10, 0.10, 0.05]))

        # Her müşteri için sabit şehir (gerçekçi)
        cust_city = str(rng.choice(CITIES, p=CITY_WEIGHTS))

        prev_date = first_date
        for _ in range(n_orders):
            delta = int(rng.integers(0, 90))
            order_date = prev_date + pd.Timedelta(days=delta)
            if order_date > datetime(2026, 5, 26):
                break
            amount = round(float(rng.uniform(50, 800)), 2)
            order_hour = int(rng.choice(range(24), p=HOUR_WEIGHTS))
            records.append({
                "customer_identifier": cust,
                "order_date": order_date.strftime("%Y-%m-%d"),
                "total_amount": amount,
                "order_number": f"TY-{seed % 10000:04d}-{int(rng.integers(1_000_000, 9_999_999))}",
                "product_name": rng.choice(products),
                "quantity": int(rng.choice([1, 1, 1, 2, 3])),
                "status": rng.choice(
                    ["Teslim Edildi", "Teslim Edildi", "Teslim Edildi", "İptal"],
                    p=[0.88, 0.05, 0.05, 0.02],
                ),
                "city": cust_city,
                "order_hour": order_hour,
            })
            prev_date = order_date

    return pd.DataFrame(records)
