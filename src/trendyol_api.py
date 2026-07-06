"""
trendyol_api.py — Trendyol Satıcı API entegrasyonu (Pro Paket özelliği).
Gerçek API çağrıları için Trendyol Satıcı Paneli'nden
API Key ve Satıcı ID alınması gerekir.

Dokümantasyon: https://developers.trendyol.com/tr/docs/category/sipari%C5%9F
"""
from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta
from typing import Any

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────────────────────────────────────
API_BASE = "https://api.trendyol.com/sapigw/suppliers"
_DEFAULT_TIMEOUT = 15  # saniye


class TrendyolAPIError(Exception):
    """API çağrısı başarısız olduğunda fırlatılır."""


# ─────────────────────────────────────────────────────────────────────────────
# API İstemcisi
# ─────────────────────────────────────────────────────────────────────────────

class TrendyolClient:
    """
    Trendyol Satıcı API istemcisi.

    Kullanım::
        client = TrendyolClient(seller_id="12345", api_key="xxx", api_secret="yyy")
        orders = client.get_orders(start_date="2025-01-01", end_date="2025-01-31")
    """

    def __init__(self, seller_id: str, api_key: str, api_secret: str) -> None:
        self.seller_id = seller_id
        self._auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Basic {self._auth}",
                "User-Agent": f"{seller_id} - SelfIntegration",
                "Content-Type": "application/json",
            }
        )

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        url = f"{API_BASE}/{self.seller_id}/{endpoint}"
        try:
            resp = self._session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            raise TrendyolAPIError(f"HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except requests.RequestException as exc:
            raise TrendyolAPIError(f"İstek hatası: {exc}") from exc

    # ── Sipariş Yönetimi ─────────────────────────────────────────────────────

    def get_orders(
        self,
        start_date: str,
        end_date: str,
        status: str = "Created",
        page: int = 0,
        size: int = 200,
    ) -> dict:
        """
        Belirtilen tarih aralığındaki siparişleri getirir.

        Args:
            start_date : "YYYY-MM-DD" formatında başlangıç tarihi
            end_date   : "YYYY-MM-DD" formatında bitiş tarihi
            status     : Created | Picking | Shipped | Delivered | UnDelivered | Cancelled | Returned
            page       : Sayfa numarası (0-indexed)
            size       : Sayfa başına kayıt (maks 200)

        Dönüş:
            Trendyol API'den gelen ham JSON yanıtı
        """
        start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        return self._get(
            "orders",
            params={
                "startDate": start_ms,
                "endDate": end_ms,
                "status": status,
                "page": page,
                "size": size,
                "orderByField": "CreatedDate",
                "orderByDirection": "DESC",
            },
        )

    def get_all_orders(self, start_date: str, end_date: str, status: str = "Delivered") -> list[dict]:
        """
        Belirtilen aralıktaki tüm siparişleri sayfalayarak çeker.
        status="ALL" verilirse Delivered+Cancelled+Returned hepsini çeker.
        Her sayfa arasında 0.3 s bekler (rate-limit).
        """
        if status == "ALL":
            result: list[dict] = []
            for s in ("Delivered", "Cancelled", "Returned"):
                result.extend(self.get_all_orders(start_date, end_date, status=s))
            return result

        all_orders: list[dict] = []
        page = 0
        while True:
            data = self.get_orders(start_date, end_date, status, page=page, size=200)
            content = data.get("content", [])
            all_orders.extend(content)

            total_pages = data.get("totalPages", 1)
            if page >= total_pages - 1 or not content:
                break
            page += 1
            time.sleep(0.3)

        return all_orders

    def get_shipment_packages(self, status: str = "Created") -> dict:
        """Kargo paket listesini döndürür."""
        return self._get("shipment-packages", params={"status": status, "size": 200})

    # ── Ürün Yönetimi ────────────────────────────────────────────────────────

    def get_products(self, page: int = 0, size: int = 100) -> dict:
        """Satıcının ürün listesini getirir."""
        return self._get("products", params={"page": page, "size": size})

    def get_all_products(self) -> list[dict]:
        """Tüm ürünleri sayfalayarak çeker."""
        products: list[dict] = []
        page = 0
        while True:
            data = self.get_products(page=page, size=200)
            content = data.get("content", [])
            products.extend(content)
            if page >= data.get("totalPages", 1) - 1 or not content:
                break
            page += 1
            time.sleep(0.3)
        return products

    # ── Ürün Soruları / Yorumları ─────────────────────────────────────────────

    def get_questions(self, page: int = 0, size: int = 50, status: str = "WaitingForAnswer") -> dict:
        """
        Ürün sorularını getirir.
        status: WaitingForAnswer | Answered | All
        """
        return self._get("questions", params={"page": page, "size": size, "status": status})

    def get_all_questions(self) -> list[dict]:
        """Tüm soruları sayfalayarak çeker (tüm statüler)."""
        questions: list[dict] = []
        for status in ("WaitingForAnswer", "Answered"):
            page = 0
            while True:
                data = self.get_questions(page=page, size=50, status=status)
                content = data.get("content", [])
                questions.extend(content)
                if page >= data.get("totalPages", 1) - 1 or not content:
                    break
                page += 1
                time.sleep(0.3)
        return questions

    def get_reviews(self, page: int = 0, size: int = 50) -> dict:
        """
        Ürün değerlendirmelerini getirir.
        Trendyol Satıcı API'de belgelenmiş endpoint: /reviews
        """
        return self._get("reviews", params={"page": page, "size": size})

    def get_all_reviews(self, max_pages: int = 10) -> list[dict]:
        """Ürün yorumlarını sayfalayarak çeker."""
        reviews: list[dict] = []
        for page in range(max_pages):
            try:
                data = self.get_reviews(page=page, size=50)
                content = data.get("content", [])
                if not content:
                    break
                reviews.extend(content)
                if page >= data.get("totalPages", 1) - 1:
                    break
                time.sleep(0.3)
            except TrendyolAPIError:
                break
        return reviews

    # ── Bağlantı Testi ───────────────────────────────────────────────────────

    def test_connection(self) -> bool:
        """API kimlik bilgilerinin geçerli olduğunu doğrular."""
        try:
            self.get_orders(
                start_date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
                size=1,
            )
            return True
        except TrendyolAPIError:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: API verisini DB formatına dönüştür
# ─────────────────────────────────────────────────────────────────────────────

def orders_to_dataframe(raw_orders: list[dict]) -> "pd.DataFrame":
    """
    Trendyol API'den gelen sipariş listesini parser.py ile uyumlu
    normalleştirilmiş DataFrame'e çevirir.
    """
    import pandas as pd

    records = []
    for o in raw_orders:
        customer_name = (
            o.get("shipmentAddress", {}).get("fullName")
            or o.get("invoiceAddress", {}).get("fullName")
            or "Bilinmiyor"
        )
        date_ms = o.get("orderDate") or o.get("createdDate", 0)
        order_dt = datetime.fromtimestamp(date_ms / 1000)
        order_date = order_dt.strftime("%Y-%m-%d")
        order_hour = order_dt.hour

        city = (
            o.get("shipmentAddress", {}).get("city")
            or o.get("invoiceAddress", {}).get("city")
            or ""
        )

        for line in o.get("lines", [o]):
            records.append(
                {
                    "order_number": str(o.get("orderNumber", "")),
                    "customer_identifier": customer_name,
                    "order_date": order_date,
                    "total_amount": float(line.get("amount", 0)),
                    "product_name": line.get("productName", ""),
                    "quantity": int(line.get("quantity", 1)),
                    "status": o.get("status", ""),
                    "city": city,
                    "order_hour": order_hour,
                }
            )
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# Credential yönetimi (DB'de şifreli saklama)
#
# CREDENTIALS_KEY env var'ı (Fernet anahtarı) ayarlıysa API secret'ları at-rest
# şifrelenir. Ayarlı değilse eskisi gibi düz metin saklanır (geriye dönük uyumlu).
# Mevcut düz-metin kayıtlar okunmaya devam eder — yalnızca yeni kayıtlar şifrelenir.
# ─────────────────────────────────────────────────────────────────────────────

_ENC_PREFIX = "enc:v1:"


def _get_fernet():
    """CREDENTIALS_KEY ayarlı ve cryptography kuruluysa Fernet nesnesi döner, yoksa None."""
    import os
    key = os.environ.get("CREDENTIALS_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception:
        return None


def _enc(value: str) -> str:
    """Değeri şifreler (anahtar yoksa olduğu gibi döner)."""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def _dec(value):
    """Şifreli değeri çözer; düz metin ise olduğu gibi döner."""
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    f = _get_fernet()
    if not f:
        return value  # anahtar kaybolduysa ham veriyi döndürme yerine olduğu gibi bırak
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return value


def save_credentials(
    user_id: int,
    seller_id: str,
    api_key: str,
    api_secret: str,
    store_id: int | None = None,
) -> None:
    """API kimlik bilgilerini veritabanına kaydeder (mağaza veya kullanıcı bazında)."""
    from src.database import get_connection
    conn = get_connection()
    _sid = str(seller_id).strip()
    _key = _enc(str(api_key).strip())
    _sec = _enc(str(api_secret).strip())
    if store_id is not None:
        conn.execute(
            "UPDATE stores SET ty_seller_id=?, ty_api_key=?, ty_api_secret=? WHERE id=? AND user_id=?",
            (_sid, _key, _sec, store_id, user_id),
        )
    else:
        conn.execute("""
            INSERT INTO user_settings (user_id, trendyol_seller_id, trendyol_api_key, trendyol_api_secret)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                trendyol_seller_id  = excluded.trendyol_seller_id,
                trendyol_api_key    = excluded.trendyol_api_key,
                trendyol_api_secret = excluded.trendyol_api_secret
        """, (user_id, _sid, _key, _sec))
    conn.commit()
    conn.close()


def load_credentials(user_id: int, store_id: int | None = None) -> dict | None:
    """
    DB'den API kimlik bilgilerini yükler.
    Döndürür: {'seller_id', 'api_key', 'api_secret', 'last_sync_at', 'last_sync_count'}
    veya None (kayıt yoksa).
    """
    from src.database import get_connection
    conn = get_connection()
    if store_id is not None:
        row = conn.execute(
            "SELECT ty_seller_id, ty_api_key, ty_api_secret, last_sync_at, last_sync_count "
            "FROM stores WHERE id=? AND user_id=?",
            (store_id, user_id),
        ).fetchone()
        conn.close()
        if not row or not row["ty_seller_id"]:
            return None
        return {
            "seller_id":       row["ty_seller_id"],
            "api_key":         _dec(row["ty_api_key"]),
            "api_secret":      _dec(row["ty_api_secret"]),
            "last_sync_at":    row["last_sync_at"],
            "last_sync_count": row["last_sync_count"] or 0,
        }
    else:
        row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if not row or not row["trendyol_seller_id"]:
            return None
        return {
            "seller_id":       row["trendyol_seller_id"],
            "api_key":         _dec(row["trendyol_api_key"]),
            "api_secret":      _dec(row["trendyol_api_secret"]),
            "last_sync_at":    row["last_sync_at"],
            "last_sync_count": row["last_sync_count"] or 0,
        }


def update_sync_time(user_id: int, count: int, store_id: int | None = None) -> None:
    """Son senkronizasyon zamanını ve sipariş sayısını günceller."""
    from src.database import get_connection
    conn = get_connection()
    if store_id is not None:
        conn.execute(
            "UPDATE stores SET last_sync_at=CURRENT_TIMESTAMP, last_sync_count=? WHERE id=? AND user_id=?",
            (count, store_id, user_id),
        )
    else:
        conn.execute("""
            INSERT INTO user_settings (user_id, last_sync_at, last_sync_count)
            VALUES (?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_sync_at    = CURRENT_TIMESTAMP,
                last_sync_count = excluded.last_sync_count
        """, (user_id, count))
    conn.commit()
    conn.close()


def sync_orders(
    user_id: int,
    start_date: str,
    end_date: str,
    store_id: int | None = None,
) -> dict:
    """
    Trendyol API'den siparişleri çeker ve DB'ye aktarır.

    Args:
        user_id    : Kullanıcı ID
        start_date : "YYYY-MM-DD"
        end_date   : "YYYY-MM-DD"
        store_id   : Mağaza ID (None → kullanıcı bazlı eski mod)

    Döndürür:
        {'success': bool, 'inserted': int, 'skipped': int, 'error': str | None}
    """
    from src.parser import import_to_db

    creds = load_credentials(user_id, store_id)
    if not creds:
        return {"success": False, "inserted": 0, "skipped": 0,
                "error": "API kimlik bilgileri bulunamadı. Veri Yükle → Trendyol API sekmesini kullanın."}

    try:
        client = TrendyolClient(creds["seller_id"], creds["api_key"], creds["api_secret"])
        raw_orders = client.get_all_orders(start_date, end_date, status="ALL")

        if not raw_orders:
            return {"success": True, "inserted": 0, "skipped": 0, "error": None}

        df = orders_to_dataframe(raw_orders)
        result = import_to_db(df, user_id, batch=f"api_{start_date}_{end_date}", store_id=store_id)
        update_sync_time(user_id, result["inserted"], store_id)

        return {
            "success": True,
            "inserted": result["inserted"],
            "skipped":  result["skipped"],
            "error":    None,
        }
    except TrendyolAPIError as exc:
        return {"success": False, "inserted": 0, "skipped": 0, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "inserted": 0, "skipped": 0, "error": f"Beklenmeyen hata: {exc}"}
