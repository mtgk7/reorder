"""
analytics.py — Retention, Cohort analizi ve LTV hesaplama motoru.
PostgreSQL ve SQLite ile uyumludur.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import streamlit as st
from src.database import get_connection


# ─────────────────────────────────────────────────────────────────────────────
# Veri çekme
# ─────────────────────────────────────────────────────────────────────────────

def _rows_to_df(rows) -> pd.DataFrame:
    """sqlite3.Row veya psycopg2 RealDictRow listesini DataFrame'e çevirir."""
    if not rows:
        return pd.DataFrame()
    # Her iki bağlantı türü de .keys() destekler
    cols = list(rows[0].keys())
    return pd.DataFrame([[r[c] for c in cols] for r in rows], columns=cols)


def _fetch_orders(user_id: int, store_id: int | None = None, conn=None) -> pd.DataFrame:
    """Kullanıcıya (veya mağazaya) ait tüm siparişleri DataFrame olarak döndürür."""
    close = conn is None
    if conn is None:
        conn = get_connection()

    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? AND store_id = ? ORDER BY order_date",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY order_date",
            (user_id,),
        ).fetchall()

    if close:
        conn.close()

    df = _rows_to_df(rows)
    if not df.empty:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df = df.dropna(subset=["order_date"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Özet metrikler (Dashboard kartları)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_summary_metrics(user_id: int, store_id: int | None = None) -> dict:
    """
    Temel dashboard metriklerini hesaplar.

    Anahtarlar:
        has_data, total_orders, unique_customers, total_revenue,
        avg_order_value, repeat_customers, repeat_rate,
        avg_ltv, top_customer_revenue
    """
    df = _fetch_orders(user_id, store_id)

    empty = {
        "has_data": False,
        "total_orders": 0,
        "unique_customers": 0,
        "total_revenue": 0.0,
        "avg_order_value": 0.0,
        "repeat_customers": 0,
        "repeat_rate": 0.0,
        "avg_ltv": 0.0,
        "top_customer_revenue": 0.0,
    }
    if df.empty:
        return empty

    total_orders = len(df)
    unique_customers = df["customer_identifier"].nunique()
    total_revenue = df["total_amount"].sum()
    avg_order_value = df["total_amount"].mean()

    cust_counts = df.groupby("customer_identifier")["id"].count()
    repeat_customers = int((cust_counts > 1).sum())
    repeat_rate = round(repeat_customers / unique_customers * 100, 1) if unique_customers else 0.0

    cust_revenue = df.groupby("customer_identifier")["total_amount"].sum()
    avg_ltv = round(float(cust_revenue.mean()), 2)
    top_customer_revenue = round(float(cust_revenue.max()), 2)

    return {
        "has_data": True,
        "total_orders": total_orders,
        "unique_customers": unique_customers,
        "total_revenue": round(total_revenue, 2),
        "avg_order_value": round(avg_order_value, 2),
        "repeat_customers": repeat_customers,
        "repeat_rate": repeat_rate,
        "avg_ltv": avg_ltv,
        "top_customer_revenue": top_customer_revenue,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cohort Retention Matrisi
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_cohort_retention(user_id: int, store_id: int | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """
    Aylık cohort retention matrisi hesaplar.

    Dönüş:
        (retention_pct_df, cohort_sizes)
        retention_pct_df  — satır=cohort ayı, sütun=Ay 0,1,2… → değer = %
        cohort_sizes      — her cohort'taki benzersiz müşteri sayısı
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty or df["customer_identifier"].nunique() < 2:
        return pd.DataFrame(), pd.Series(dtype=int)

    # İlk alışveriş tarihi → cohort ayı
    first_buy = (
        df.groupby("customer_identifier")["order_date"]
        .min()
        .dt.to_period("M")
        .rename("cohort_month")
    )
    df = df.join(first_buy, on="customer_identifier")
    df["order_month"] = df["order_date"].dt.to_period("M")
    df["months_since_first"] = (df["order_month"] - df["cohort_month"]).apply(
        lambda x: x.n if hasattr(x, "n") else int(x)
    )

    # Cohort × ay — benzersiz müşteri sayısı
    pivot = (
        df.groupby(["cohort_month", "months_since_first"])["customer_identifier"]
        .nunique()
        .unstack(fill_value=0)
    )

    cohort_sizes = pivot.get(0, pd.Series(dtype=int))
    if cohort_sizes.empty:
        return pd.DataFrame(), pd.Series(dtype=int)

    # % bazına çevir
    retention_pct = pivot.div(cohort_sizes, axis=0).mul(100).round(1)
    return retention_pct, cohort_sizes.astype(int)


# ─────────────────────────────────────────────────────────────────────────────
# Aylık trend (grafik verisi)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_monthly_trend(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """
    Her ay için sipariş sayısı, gelir ve benzersiz müşteri sayısını döndürür.
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return pd.DataFrame()

    df["month"] = df["order_date"].dt.to_period("M")

    monthly = (
        df.groupby("month")
        .agg(
            orders=("id", "count"),
            revenue=("total_amount", "sum"),
            unique_customers=("customer_identifier", "nunique"),
        )
        .reset_index()
    )
    monthly["month_str"] = monthly["month"].astype(str)
    return monthly


@st.cache_data(ttl=60)
def get_new_vs_returning(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """
    Aylık yeni / geri dönen müşteri ayrımı.
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return pd.DataFrame()

    first_buy = df.groupby("customer_identifier")["order_date"].min().dt.to_period("M")
    df["month"] = df["order_date"].dt.to_period("M")
    df = df.join(first_buy.rename("first_month"), on="customer_identifier")
    df["is_new"] = df["month"] == df["first_month"]

    summary = (
        df.groupby(["month", "is_new"])["customer_identifier"]
        .nunique()
        .unstack(fill_value=0)
        .reset_index()
    )
    summary.columns.name = None
    summary = summary.rename(columns={True: "yeni_musteri", False: "geri_donen"})
    summary["month_str"] = summary["month"].astype(str)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Müşteri Segmentasyonu (RFM tabanlı)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_customer_segments(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """
    Her müşteri için basit RFM-tabanlı segment atar.

    Segmentler:
        Sadık Müşteri | Gelişen Müşteri | Yeni Müşteri |
        Risk Altında  | Tek Alışveriş   | Kaybolma Riski
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now()

    stats = (
        df.groupby("customer_identifier")
        .agg(
            total_orders=("id", "count"),
            total_revenue=("total_amount", "sum"),
            first_purchase=("order_date", "min"),
            last_purchase=("order_date", "max"),
        )
        .reset_index()
    )
    stats["avg_order_value"] = (stats["total_revenue"] / stats["total_orders"]).round(2)
    stats["days_since_last"] = (now - stats["last_purchase"]).dt.days

    def _segment(row: pd.Series) -> str:
        orders = row["total_orders"]
        days = row["days_since_last"]
        if orders == 1:
            return "Yeni Müşteri" if days <= 90 else "Tek Alışveriş"
        if orders <= 3:
            return "Gelişen Müşteri" if days <= 90 else "Risk Altında"
        return "Sadık Müşteri" if days <= 90 else "Kaybolma Riski"

    stats["segment"] = stats.apply(_segment, axis=1)

    def _churn(row: pd.Series) -> int:
        recency  = min(int(row["days_since_last"]) / 180 * 40, 40)
        freq     = max(40 - int(row["total_orders"]) * 8, 0)
        rev_norm = min(float(row["total_revenue"]) / 500, 1.0)
        monetary = (1 - rev_norm) * 20
        return min(int(recency + freq + monetary), 100)

    stats["churn_score"] = stats.apply(_churn, axis=1)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# LTV Dağılımı
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_ltv_distribution(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """Müşteri başı toplam harcama dağılımını döndürür."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return pd.DataFrame()

    ltv = (
        df.groupby("customer_identifier")["total_amount"]
        .sum()
        .reset_index()
        .rename(columns={"customer_identifier": "musteri", "total_amount": "ltv"})
        .sort_values("ltv", ascending=False)
    )
    return ltv


@st.cache_data(ttl=60)
def get_top_customers(user_id: int, n: int = 10, store_id: int | None = None) -> pd.DataFrame:
    """En yüksek LTV'li N müşteriyi döndürür."""
    df = get_ltv_distribution(user_id, store_id)
    if df.empty:
        return pd.DataFrame()
    return df.head(n).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Mini Dashboard — Sipariş Analitiği (KPI + Ürün + Günlük Ciro)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_order_status_kpis(user_id: int, store_id: int | None = None) -> dict:
    """
    Toplam ciro, bekleyen (Pending) ve tamamlanan (Completed) sipariş sayıları.

    Anahtarlar:
        total_revenue, pending, completed
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"total_revenue": 0.0, "pending": 0, "completed": 0}

    total_revenue = float(df["total_amount"].sum())

    status_col = df.get("status", pd.Series(dtype=str))
    status_lower = status_col.fillna("").str.strip().str.lower()
    # Türkçe ve İngilizce status değerlerini kapsıyoruz
    pending_vals   = {"pending", "işlemde", "hazırlanıyor", "beklemede"}
    completed_vals = {"completed", "teslim edildi", "delivered", "tamamlandı"}
    pending   = int(status_lower.isin(pending_vals).sum())
    completed = int(status_lower.isin(completed_vals).sum())

    return {
        "total_revenue": round(total_revenue, 2),
        "pending":       pending,
        "completed":     completed,
    }


@st.cache_data(ttl=60)
def get_top_products(user_id: int, n: int = 10, store_id: int | None = None) -> pd.DataFrame:
    """
    En çok satan ürünler — ürün adı başına toplam miktar ve gelir.

    Ürün miktarını önce `quantity` sütunundan okur.
    Sütun yoksa veya 0 ise product_name içindeki "x<N>" kalıbından çıkarır.
    Dönüş sütunları: product_name, total_qty, total_revenue
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty or "product_name" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["product_name"])
    df = df[df["product_name"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame()

    # Miktar belirleme: quantity sütunu → "x2" kalıbı → varsayılan 1
    if "quantity" in df.columns:
        df["_qty"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    else:
        df["_qty"] = 0

    # quantity 0 veya NaN olan satırlar için product_name'den "x<N>" ayıkla
    mask_zero = df["_qty"] <= 0
    if mask_zero.any():
        import re as _re
        extracted = df.loc[mask_zero, "product_name"].apply(
            lambda name: int(m.group(1)) if (m := _re.search(r"[xX×]\s*(\d+)\s*$", str(name))) else 1
        )
        df.loc[mask_zero, "_qty"] = extracted

    products = (
        df.groupby("product_name", sort=False)
        .agg(total_qty=("_qty", "sum"), total_revenue=("total_amount", "sum"))
        .reset_index()
        .sort_values("total_qty", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    return products


@st.cache_data(ttl=60)
def get_daily_revenue(user_id: int, days: int = 30, store_id: int | None = None) -> pd.DataFrame:
    """
    Günlük ciro trendi.

    Son `days` günü filtreler; bu aralıkta veri yoksa tüm geçmiş kullanılır.
    Dönüş sütunları: date_str, revenue, orders
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return pd.DataFrame()

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    recent = df[df["order_date"] >= cutoff]
    source = recent if not recent.empty else df

    daily = (
        source.groupby(source["order_date"].dt.date)
        .agg(revenue=("total_amount", "sum"), orders=("id", "count"))
        .reset_index()
        .rename(columns={"order_date": "date"})
        .sort_values("date")
    )
    daily["date_str"] = daily["date"].astype(str)
    return daily


# ─────────────────────────────────────────────────────────────────────────────
# Müşteri Detay (Özellik 2)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_customer_detail(
    user_id: int,
    customer_identifier: str,
    store_id: int | None = None,
) -> dict:
    """Tek müşteri için tüm sipariş geçmişi ve istatistikleri döndürür."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {}

    cdf = df[df["customer_identifier"] == customer_identifier].copy()
    if cdf.empty:
        return {}

    cdf = cdf.sort_values("order_date").reset_index(drop=True)
    cdf["cumulative_ltv"] = cdf["total_amount"].cumsum()
    cdf["date_str"] = cdf["order_date"].dt.strftime("%Y-%m-%d")

    total_orders   = len(cdf)
    total_revenue  = round(float(cdf["total_amount"].sum()), 2)
    avg_order      = round(float(cdf["total_amount"].mean()), 2)
    first_date     = cdf["order_date"].min()
    last_date      = cdf["order_date"].max()
    days_since     = int((pd.Timestamp.now() - last_date).days)
    span_days      = max(int((last_date - first_date).days), 1)

    # Segment
    if total_orders == 1:
        segment = "Yeni Müşteri" if days_since <= 90 else "Tek Alışveriş"
    elif total_orders <= 3:
        segment = "Gelişen Müşteri" if days_since <= 90 else "Risk Altında"
    else:
        segment = "Sadık Müşteri" if days_since <= 90 else "Kaybolma Riski"

    # Churn score
    recency  = min(days_since / 180 * 40, 40)
    freq     = max(40 - total_orders * 8, 0)
    rev_norm = min(total_revenue / 500, 1.0)
    churn_score = min(int(recency + freq + (1 - rev_norm) * 20), 100)

    # Aylık harcama
    monthly = (
        cdf.groupby(cdf["order_date"].dt.to_period("M"))["total_amount"]
        .sum()
        .reset_index()
    )
    monthly.columns = ["month", "revenue"]
    monthly["month_str"] = monthly["month"].astype(str)

    return {
        "orders":        cdf,
        "monthly":       monthly,
        "total_orders":  total_orders,
        "total_revenue": total_revenue,
        "avg_order":     avg_order,
        "first_date":    first_date.strftime("%d.%m.%Y"),
        "last_date":     last_date.strftime("%d.%m.%Y"),
        "days_since":    days_since,
        "span_days":     span_days,
        "segment":       segment,
        "churn_score":   churn_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Hedef / KPI — Bu ayki ilerleme (Özellik 3)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_current_month_metrics(user_id: int, store_id: int | None = None) -> dict:
    """Bu ayki gelir, yeni müşteri sayısı ve retention oranını döndürür."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"revenue": 0.0, "new_customers": 0, "retention_rate": 0.0, "orders": 0}

    now    = pd.Timestamp.now()
    period = now.to_period("M")
    this_m = df[df["order_date"].dt.to_period("M") == period]

    revenue   = round(float(this_m["total_amount"].sum()), 2)
    orders    = int(len(this_m))

    # Yeni müşteri: bu ay ilk kez alışveriş yapan
    first_buy = df.groupby("customer_identifier")["order_date"].min().dt.to_period("M")
    new_custs = int((first_buy == period).sum())

    # Retention: bu ay sipariş veren müşterilerden geçen ay da veren kaçı
    prev_period   = (now - pd.DateOffset(months=1)).to_period("M")
    prev_buyers   = set(df[df["order_date"].dt.to_period("M") == prev_period]["customer_identifier"])
    this_buyers   = set(this_m["customer_identifier"])
    retained      = len(prev_buyers & this_buyers)
    ret_rate      = round(retained / len(prev_buyers) * 100, 1) if prev_buyers else 0.0

    return {
        "revenue":        revenue,
        "new_customers":  new_custs,
        "retention_rate": ret_rate,
        "orders":         orders,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ürün × Müşteri Analizi (Özellik 4)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_product_analysis(user_id: int, store_id: int | None = None) -> dict:
    """
    Ürün bazlı müşteri davranışı:
    - Her ürünü satın alan müşterilerin tekrar alım oranı
    - En yüksek LTV üreticisi ürünler
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty or "product_name" not in df.columns:
        return {"retention": pd.DataFrame(), "ltv": pd.DataFrame()}

    df = df.dropna(subset=["product_name"]).copy()
    df = df[df["product_name"].str.strip() != ""]
    if df.empty:
        return {"retention": pd.DataFrame(), "ltv": pd.DataFrame()}

    order_counts = df.groupby("customer_identifier")["id"].count()

    rows = []
    for product, grp in df.groupby("product_name"):
        buyers = grp["customer_identifier"].unique()
        repeat = int(sum(1 for b in buyers if order_counts.get(b, 1) > 1))
        rows.append({
            "product_name":   str(product),
            "buyer_count":    len(buyers),
            "repeat_buyers":  repeat,
            "retention_rate": round(repeat / len(buyers) * 100, 1) if len(buyers) else 0.0,
            "total_revenue":  round(float(grp["total_amount"].sum()), 2),
            "avg_revenue_per_buyer": round(float(grp["total_amount"].sum()) / len(buyers), 2),
        })

    df_ret = (
        pd.DataFrame(rows)
        .sort_values("buyer_count", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )

    df_ltv = (
        pd.DataFrame(rows)
        .sort_values("avg_revenue_per_buyer", ascending=False)
        .head(15)
        .reset_index(drop=True)
    )

    return {"retention": df_ret, "ltv": df_ltv}
