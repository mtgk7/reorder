"""
hepsiburada_api.py — Hepsiburada Merchant API entegrasyonu.
Gerçek API çağrıları için Hepsiburada Satıcı Paneli'nden Merchant ID,
kullanıcı adı ve şifre alınması gerekir.

Dokümantasyon: https://developers.hepsiburada.com/

Not: Tarih filtresi parametre adları ve response alan adları resmi
dokümantasyondan doğrudan doğrulanamadı (site scraping korumalı). İlk gerçek
senkronizasyondan sonra `orders_to_dataframe`'deki alan eşlemesi gerçek
veriyle karşılaştırılıp gerekirse düzeltilmelidir (Trendyol entegrasyonunda
da aynı şekilde ilerlenmişti).
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import requests

from src.credentials_crypto import enc as _enc, dec as _dec

_BASE_URL = "https://oms-external.hepsiburada.com"
_DEFAULT_TIMEOUT = 15  # saniye


class HepsiburadaAPIError(Exception):
    """API çağrısı başarısız olduğunda fırlatılır."""


# ─────────────────────────────────────────────────────────────────────────────
# API İstemcisi
# ─────────────────────────────────────────────────────────────────────────────

class HepsiburadaClient:
    """
    Hepsiburada Merchant API istemcisi.

    Kullanım::
        client = HepsiburadaClient(merchant_id="xxxx-xxxx", username="xxx", password="yyy")
        orders = client.get_all_orders(start_date="2025-01-01", end_date="2025-01-31")
    """

    def __init__(self, merchant_id: str, username: str, password: str) -> None:
        self.merchant_id = merchant_id
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            }
        )

    def get_orders(
        self,
        offset: int = 0,
        limit: int = 100,
        begin_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """
        Ödemesi tamamlanmış siparişleri getirir.

        Args:
            offset     : Sayfalama başlangıcı
            limit      : Sayfa başına kayıt
            begin_date : "YYYY-MM-DD HH:MM" formatında başlangıç tarihi (opsiyonel)
            end_date   : "YYYY-MM-DD HH:MM" formatında bitiş tarihi (opsiyonel)

        Dönüş:
            Hepsiburada API'den gelen ham sipariş listesi
        """
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date

        url = f"{_BASE_URL}/orders/merchantid/{self.merchant_id}"
        try:
            resp = self._session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
            if resp.status_code == 401:
                raise HepsiburadaAPIError("HTTP 401: Geçersiz API kimlik bilgileri.")
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as exc:
            raise HepsiburadaAPIError(f"HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except requests.RequestException as exc:
            raise HepsiburadaAPIError(f"İstek hatası: {exc}") from exc

        # Response ya doğrudan liste ya da {"items": [...]} / {"orders": [...]} şeklinde olabilir
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items") or data.get("orders") or data.get("data") or []
        return []

    def get_all_orders(self, start_date: str, end_date: str) -> list[dict]:
        """
        Belirtilen aralıktaki tüm siparişleri sayfalayarak çeker.
        Dönen kayıt sayısı `limit`'ten azsa son sayfa kabul edilir.
        """
        begin = f"{start_date} 00:00"
        end = f"{end_date} 23:59"

        all_orders: list[dict] = []
        offset = 0
        limit = 100
        while True:
            page = self.get_orders(offset=offset, limit=limit, begin_date=begin, end_date=end)
            if not page:
                break
            all_orders.extend(page)
            if len(page) < limit:
                break
            offset += limit
        return all_orders

    def test_connection(self) -> bool:
        """API kimlik bilgilerinin geçerli olduğunu doğrular."""
        try:
            sample = self.get_orders(offset=0, limit=1)
            print(f"[HepsiburadaClient] Bağlantı başarılı. Örnek kayıt anahtarları: "
                  f"{list(sample[0].keys()) if sample else '(sipariş yok)'}", flush=True)
            return True
        except HepsiburadaAPIError:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: API verisini DB formatına dönüştür
# ─────────────────────────────────────────────────────────────────────────────

def orders_to_dataframe(raw_orders: list[dict]) -> "pd.DataFrame":
    """
    Hepsiburada API'den gelen sipariş listesini parser.py ile uyumlu
    normalleştirilmiş DataFrame'e çevirir.
    """
    import pandas as pd

    records = []
    for o in raw_orders:
        o = o or {}
        customer_name = o.get("customerName") or o.get("recipientName") or o.get("customerFullName") or "Bilinmiyor"
        city = o.get("city") or o.get("shippingCity") or ""

        date_raw = o.get("orderDate") or o.get("createdDate") or o.get("dueDate")
        order_date, order_hour = None, None
        if date_raw:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(str(date_raw)[: len(fmt) + 2], fmt)
                    order_date, order_hour = dt.strftime("%Y-%m-%d"), dt.hour
                    break
                except ValueError:
                    continue
        if not order_date:
            order_date = datetime.now().strftime("%Y-%m-%d")

        def _num(val, default, cast):
            try:
                return cast(val)
            except (TypeError, ValueError):
                return default

        lines = o.get("items") or o.get("lines") or [o]
        for line in lines:
            line = line or {}
            records.append(
                {
                    "order_number": str(o.get("orderNumber") or o.get("id") or ""),
                    "customer_identifier": customer_name,
                    "order_date": order_date,
                    "total_amount": _num(line.get("totalPrice") or line.get("price") or line.get("amount"), 0.0, float),
                    "product_name": line.get("productName") or line.get("name") or "",
                    "quantity": _num(line.get("quantity"), 1, int),
                    "status": o.get("status") or o.get("orderStatus") or "",
                    "city": city,
                    "order_hour": order_hour,
                }
            )
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# Credential yönetimi (mağaza bazlı — Hepsiburada çok-mağaza döneminde eklendi)
# ─────────────────────────────────────────────────────────────────────────────

def save_credentials(user_id: int, merchant_id: str, username: str, password: str, store_id: int) -> None:
    """API kimlik bilgilerini veritabanına kaydeder (mağaza bazında)."""
    from src.database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE stores SET hb_merchant_id=?, hb_username=?, hb_password=? WHERE id=? AND user_id=?",
        (str(merchant_id).strip(), str(username).strip(), _enc(str(password).strip()), store_id, user_id),
    )
    conn.commit()
    conn.close()


def load_credentials(user_id: int, store_id: int) -> dict | None:
    """
    DB'den API kimlik bilgilerini yükler.
    Döndürür: {'merchant_id', 'username', 'password', 'last_sync_at', 'last_sync_count'}
    veya None (kayıt yoksa).
    """
    from src.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT hb_merchant_id, hb_username, hb_password, last_sync_at, last_sync_count "
        "FROM stores WHERE id=? AND user_id=?",
        (store_id, user_id),
    ).fetchone()
    conn.close()
    if not row or not row["hb_merchant_id"]:
        return None
    return {
        "merchant_id":     row["hb_merchant_id"],
        "username":        row["hb_username"],
        "password":        _dec(row["hb_password"]),
        "last_sync_at":    row["last_sync_at"],
        "last_sync_count": row["last_sync_count"] or 0,
    }


def update_sync_time(store_id: int, user_id: int, count: int) -> None:
    """Son senkronizasyon zamanını ve sipariş sayısını günceller."""
    from src.database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE stores SET last_sync_at=CURRENT_TIMESTAMP, last_sync_count=? WHERE id=? AND user_id=?",
        (count, store_id, user_id),
    )
    conn.commit()
    conn.close()


def sync_orders(user_id: int, start_date: str, end_date: str, store_id: int) -> dict:
    """
    Hepsiburada API'den siparişleri çeker ve DB'ye aktarır.

    Döndürür:
        {'success': bool, 'inserted': int, 'skipped': int, 'error': str | None}
    """
    from src.parser import import_to_db

    creds = load_credentials(user_id, store_id)
    if not creds:
        return {"success": False, "inserted": 0, "skipped": 0,
                "error": "API kimlik bilgileri bulunamadı. Veri Yükle → API Bağlantısı sekmesini kullanın."}

    try:
        client = HepsiburadaClient(creds["merchant_id"], creds["username"], creds["password"])
        raw_orders = client.get_all_orders(start_date, end_date)

        # Alan adı doğrulaması henüz yapılamadı (bkz. modül docstring'i) — ilk gerçek
        # senkronda ham veriyi UI'da gösterebilmek için bir örnek kaydı sonuca ekliyoruz.
        raw_sample = raw_orders[0] if raw_orders else None

        if not raw_orders:
            return {"success": True, "inserted": 0, "skipped": 0, "error": None, "raw_sample": None}

        df = orders_to_dataframe(raw_orders)
        result = import_to_db(df, user_id, batch=f"hb_api_{start_date}_{end_date}", store_id=store_id)
        update_sync_time(store_id, user_id, result["inserted"])

        print(f"[hepsiburada_api.sync_orders] {len(raw_orders)} ham sipariş alındı. "
              f"Örnek anahtarlar: {list(raw_sample.keys()) if raw_sample else '(yok)'}", flush=True)

        return {
            "success": True,
            "inserted": result["inserted"],
            "skipped":  result["skipped"],
            "error":    None,
            "raw_sample": raw_sample,
        }
    except HepsiburadaAPIError as exc:
        return {"success": False, "inserted": 0, "skipped": 0, "error": str(exc), "raw_sample": None}
    except Exception as exc:
        return {"success": False, "inserted": 0, "skipped": 0, "error": f"Beklenmeyen hata: {exc}", "raw_sample": None}
