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


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_orders(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """Kullanıcıya (veya mağazaya) ait tüm siparişleri döndürür.
    300s önbellek: tüm analytics fonksiyonları tek DB sorgusunu paylaşır."""
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
    conn.close()
    df = _rows_to_df(rows)
    if not df.empty:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df = df.dropna(subset=["order_date"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Özet metrikler (Dashboard kartları)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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


@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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


@st.cache_data(ttl=1800, show_spinner=False)
def get_top_customers(user_id: int, n: int = 10, store_id: int | None = None) -> pd.DataFrame:
    """En yüksek LTV'li N müşteriyi döndürür."""
    df = get_ltv_distribution(user_id, store_id)
    if df.empty:
        return pd.DataFrame()
    return df.head(n).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Mini Dashboard — Sipariş Analitiği (KPI + Ürün + Günlük Ciro)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
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


@st.cache_data(ttl=1800, show_spinner=False)
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


@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
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


# ─────────────────────────────────────────────────────────────────────────────
# Gelir Tahmini (Özellik: Tahmin)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_revenue_forecast(
    user_id: int,
    store_id: int | None = None,
    horizon_days: int = 90,
) -> dict:
    """
    Geçmiş aylık gelir verisine dayalı basit lineer trend tahmini.

    Dönüş:
        history  — gerçek aylık gelir (month_str, revenue)
        forecast — tahmin edilen günlük gelir (date_str, revenue, lower, upper)
        trend    — "artış" | "düşüş" | "sabit"
        monthly_growth — aylık ortalama büyüme oranı (%)
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"history": pd.DataFrame(), "forecast": pd.DataFrame(), "trend": "sabit", "monthly_growth": 0.0}

    monthly = (
        df.groupby(df["order_date"].dt.to_period("M"))["total_amount"]
        .sum()
        .reset_index()
    )
    monthly.columns = ["month", "revenue"]
    monthly["month_str"] = monthly["month"].astype(str)
    monthly["month_idx"] = range(len(monthly))

    if len(monthly) < 2:
        return {"history": monthly, "forecast": pd.DataFrame(), "trend": "sabit", "monthly_growth": 0.0}

    x = monthly["month_idx"].values
    y = monthly["revenue"].values

    # Ağırlıklı lineer regresyon (yakın aylar daha önemli)
    weights = np.exp(0.15 * x)
    w_mean_x = np.average(x, weights=weights)
    w_mean_y = np.average(y, weights=weights)
    slope = np.sum(weights * (x - w_mean_x) * (y - w_mean_y)) / np.sum(weights * (x - w_mean_x) ** 2)
    intercept = w_mean_y - slope * w_mean_x

    # Residual standart sapması (güven aralığı için)
    y_pred_hist = slope * x + intercept
    residuals = y - y_pred_hist
    sigma = float(np.std(residuals)) if len(residuals) > 1 else float(np.mean(y) * 0.15)

    # Tahmin: horizon_days gün için günlük tahmin
    last_date = df["order_date"].max()
    avg_daily = float(np.mean(y)) / 30.0
    n_months = len(monthly)

    forecast_rows = []
    for d in range(1, horizon_days + 1):
        future_date = last_date + pd.Timedelta(days=d)
        month_offset = n_months - 1 + d / 30.0
        daily_rev = max((slope * month_offset + intercept) / 30.0, 0.0)
        lower = max(daily_rev - sigma / 30.0, 0.0)
        upper = daily_rev + sigma / 30.0
        forecast_rows.append({
            "date_str": future_date.strftime("%Y-%m-%d"),
            "revenue": round(daily_rev, 2),
            "lower": round(lower, 2),
            "upper": round(upper, 2),
        })
    forecast_df = pd.DataFrame(forecast_rows)

    # Aylık büyüme
    if len(y) >= 2:
        recent = float(np.mean(y[-3:])) if len(y) >= 3 else float(y[-1])
        prev   = float(np.mean(y[-6:-3])) if len(y) >= 6 else float(y[0])
        monthly_growth = round((recent - prev) / prev * 100, 1) if prev > 0 else 0.0
    else:
        monthly_growth = 0.0

    trend = "artış" if slope > 0 else ("düşüş" if slope < 0 else "sabit")

    return {
        "history":        monthly,
        "forecast":       forecast_df,
        "trend":          trend,
        "monthly_growth": monthly_growth,
        "slope":          round(float(slope), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ürün Öneri Matrisi / Cross-Sell (Özellik)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_cross_sell_matrix(
    user_id: int,
    store_id: int | None = None,
    top_n: int = 8,
) -> pd.DataFrame:
    """
    Birlikte satın alınan ürün çiftlerini bulur.

    Dönüş: product_a, product_b, co_buyers, confidence_ab, confidence_ba
        co_buyers    — her iki ürünü de alan müşteri sayısı
        confidence_a — A alanların kaçı B'yi de aldı (%)
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty or "product_name" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["product_name"]).copy()
    df = df[df["product_name"].str.strip() != ""]
    if df.empty:
        return pd.DataFrame()

    # Müşteri → ürün seti
    customer_products = (
        df.groupby("customer_identifier")["product_name"]
        .apply(set)
        .reset_index()
    )

    # Sadece 2+ ürün alan müşteriler
    multi = customer_products[customer_products["product_name"].apply(len) >= 2]
    if len(multi) < 3:
        return pd.DataFrame()

    # Ürün başına alıcı sayısı
    product_buyers: dict[str, set] = {}
    for _, row in customer_products.iterrows():
        for p in row["product_name"]:
            product_buyers.setdefault(p, set()).add(row["customer_identifier"])

    # En popüler top_n ürün seç (matrisi küçük tut)
    top_products = sorted(product_buyers, key=lambda p: len(product_buyers[p]), reverse=True)[:top_n]

    pairs = []
    for i, a in enumerate(top_products):
        for b in top_products[i + 1:]:
            buyers_a = product_buyers[a]
            buyers_b = product_buyers[b]
            co = buyers_a & buyers_b
            if not co:
                continue
            conf_ab = round(len(co) / len(buyers_a) * 100, 1) if buyers_a else 0.0
            conf_ba = round(len(co) / len(buyers_b) * 100, 1) if buyers_b else 0.0
            pairs.append({
                "product_a":     a[:40],
                "product_b":     b[:40],
                "co_buyers":     len(co),
                "confidence_ab": conf_ab,
                "confidence_ba": conf_ba,
                "lift":          round(conf_ab / (len(buyers_b) / len(customer_products)) / 100, 2)
                                 if len(customer_products) else 0.0,
            })

    if not pairs:
        return pd.DataFrame()

    return (
        pd.DataFrame(pairs)
        .sort_values("co_buyers", ascending=False)
        .head(30)
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Karşılaştırmalı Dönem Analizi (Özellik)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_period_comparison(
    user_id: int,
    store_id: int | None = None,
    mode: str = "month",  # "month" | "year"
) -> dict:
    """
    Bu dönem vs önceki dönem karşılaştırması.

    mode="month" → bu ay vs geçen ay
    mode="year"  → bu yıl vs geçen yıl (yıl başından bugüne)

    Dönüş anahtarları:
        current, previous — her biri: revenue, orders, unique_customers, avg_order
        delta_revenue_pct, delta_orders_pct, delta_customers_pct
        daily_current, daily_previous — günlük gelir karşılaştırması için
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {}

    now = pd.Timestamp.now()

    if mode == "month":
        cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end   = cur_start - pd.Timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    else:  # year
        cur_start  = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end   = cur_start - pd.Timedelta(days=1)
        prev_start = prev_end.replace(month=1, day=1)

    cur_df  = df[(df["order_date"] >= cur_start) & (df["order_date"] <= now)]
    prev_df = df[(df["order_date"] >= prev_start) & (df["order_date"] <= prev_end)]

    def _agg(d: pd.DataFrame) -> dict:
        if d.empty:
            return {"revenue": 0.0, "orders": 0, "unique_customers": 0, "avg_order": 0.0}
        return {
            "revenue":          round(float(d["total_amount"].sum()), 2),
            "orders":           len(d),
            "unique_customers": d["customer_identifier"].nunique(),
            "avg_order":        round(float(d["total_amount"].mean()), 2),
        }

    def _pct(cur, prev) -> float:
        if not prev:
            return 0.0
        return round((cur - prev) / prev * 100, 1)

    cur_agg  = _agg(cur_df)
    prev_agg = _agg(prev_df)

    # Günlük karşılaştırma (grafik için)
    def _daily(d: pd.DataFrame, label: str) -> pd.DataFrame:
        if d.empty:
            return pd.DataFrame()
        daily = (
            d.groupby(d["order_date"].dt.day)["total_amount"]
            .sum()
            .reset_index()
        )
        daily.columns = ["gun", "revenue"]
        daily["seri"] = label
        return daily

    daily_cur  = _daily(cur_df,  "Bu Dönem")
    daily_prev = _daily(prev_df, "Önceki Dönem")

    return {
        "current":              cur_agg,
        "previous":             prev_agg,
        "delta_revenue_pct":    _pct(cur_agg["revenue"],          prev_agg["revenue"]),
        "delta_orders_pct":     _pct(cur_agg["orders"],           prev_agg["orders"]),
        "delta_customers_pct":  _pct(cur_agg["unique_customers"], prev_agg["unique_customers"]),
        "daily_current":        daily_cur,
        "daily_previous":       daily_prev,
        "mode":                 mode,
        "cur_label":            "Bu Ay"  if mode == "month" else "Bu Yıl",
        "prev_label":           "Geçen Ay" if mode == "month" else "Geçen Yıl",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Anlık Bildirim / Anomali Tespiti (Özellik)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_anomalies(user_id: int, store_id: int | None = None) -> list[dict]:
    """
    Son 7 günlük veride anlamlı sapmaları tespit eder.

    Döndüğü uyarı tipleri:
        revenue_drop  — günlük gelir son 3 gün %30+ düştü
        revenue_spike — günlük gelir son 3 gün %50+ arttı
        big_order     — tek siparişin değeri ortalama sipariş x 5+
        churn_spike   — churn_score > 80 olan müşteri sayısı toplam müşterinin %20'sini geçti
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return []

    alerts = []
    now = pd.Timestamp.now()

    # Günlük gelir anomalisi
    daily = (
        df.groupby(df["order_date"].dt.date)["total_amount"]
        .sum()
        .sort_index()
    )
    if len(daily) >= 10:
        baseline_avg = float(daily.iloc[:-3].mean())
        recent_avg   = float(daily.iloc[-3:].mean())
        if baseline_avg > 0:
            chg = (recent_avg - baseline_avg) / baseline_avg
            if chg <= -0.30:
                alerts.append({
                    "type":    "revenue_drop",
                    "icon":    "🔴",
                    "title":   "Gelir Düşüşü",
                    "message": f"Son 3 gün geliri ortalamanın %{abs(chg*100):.0f} altında.",
                    "severity": "high",
                })
            elif chg >= 0.50:
                alerts.append({
                    "type":    "revenue_spike",
                    "icon":    "🟢",
                    "title":   "Gelir Artışı",
                    "message": f"Son 3 gün geliri ortalamanın %{chg*100:.0f} üstünde!",
                    "severity": "low",
                })

    # Büyük sipariş
    avg_order = float(df["total_amount"].mean()) if not df.empty else 0
    recent_orders = df[df["order_date"] >= now - pd.Timedelta(days=7)]
    if not recent_orders.empty and avg_order > 0:
        big = recent_orders[recent_orders["total_amount"] >= avg_order * 5]
        if not big.empty:
            biggest = float(big["total_amount"].max())
            alerts.append({
                "type":    "big_order",
                "icon":    "💰",
                "title":   "Büyük Sipariş",
                "message": f"Son 7 günde {_fmt_tl_plain(biggest)} tutarında yüksek değerli sipariş.",
                "severity": "low",
            })

    return alerts


def _fmt_tl_plain(val: float) -> str:
    return f"₺{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ─────────────────────────────────────────────────────────────────────────────
# Segment Aksiyon Önerileri (Özellik)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_segment_recommendations(user_id: int, store_id: int | None = None) -> list[dict]:
    """
    Her müşteri segmenti için aksiyon önerileri üretir.

    Dönüş: list[dict] — her eleman bir segment + öneri bloğu
    """
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return []

    segments_df = get_customer_segments(user_id, store_id)
    if segments_df.empty:
        return []

    seg_counts = segments_df.groupby("segment")["customer_identifier"].count().to_dict()
    seg_revenue = segments_df.groupby("segment")["total_revenue"].sum().to_dict()
    high_churn = segments_df[segments_df["churn_score"] >= 70]

    recs = []

    # Kaybolma Riski
    if seg_counts.get("Kaybolma Riski", 0) > 0:
        cnt = seg_counts["Kaybolma Riski"]
        rev = seg_revenue.get("Kaybolma Riski", 0)
        recs.append({
            "segment":  "Kaybolma Riski",
            "color":    "#6B7280",
            "icon":     "😴",
            "count":    cnt,
            "revenue":  rev,
            "priority": "YÜKSEK",
            "priority_color": "#EF4444",
            "actions": [
                "E-posta kampanyası ile %15 indirim kodu gönder",
                f"{cnt} müşteriyi WhatsApp'ta kişisel mesajla ulaş",
                "Önceki sipariş ürününü hatırlatan öneride bulun",
            ],
            "expected_impact": f"₺{rev*0.15:,.0f} potansiyel geri kazanım",
        })

    # Risk Altında
    if seg_counts.get("Risk Altında", 0) > 0:
        cnt = seg_counts["Risk Altında"]
        rev = seg_revenue.get("Risk Altında", 0)
        recs.append({
            "segment":  "Risk Altında",
            "color":    "#EF4444",
            "icon":     "⚠️",
            "count":    cnt,
            "revenue":  rev,
            "priority": "ORTA",
            "priority_color": "#F59E0B",
            "actions": [
                "Proaktif müşteri memnuniyeti anketi gönder",
                "Bağlılık kampanyası ile ücretsiz kargo / hediye çeki teklif et",
                "Churn skoru 80+ olanları öncelikli ele al",
            ],
            "expected_impact": f"{cnt} müşteriyi koruma altına al",
        })

    # Yeni Müşteri → İkinci alışveriş
    if seg_counts.get("Yeni Müşteri", 0) > 0:
        cnt = seg_counts["Yeni Müşteri"]
        recs.append({
            "segment":  "Yeni Müşteri",
            "color":    "#F59E0B",
            "icon":     "🌱",
            "count":    cnt,
            "revenue":  seg_revenue.get("Yeni Müşteri", 0),
            "priority": "ORTA",
            "priority_color": "#3B82F6",
            "actions": [
                "İlk siparişten 7 gün sonra takip e-postası gönder",
                "İkinci alışverişe özel %10 hoş geldin indirimi sun",
                "İlgi alanlarına göre ürün önerileri paylaş",
            ],
            "expected_impact": "2. alışveriş dönüşüm oranını artır",
        })

    # Sadık Müşteri → LTV artırımı
    if seg_counts.get("Sadık Müşteri", 0) > 0:
        cnt = seg_counts["Sadık Müşteri"]
        rev = seg_revenue.get("Sadık Müşteri", 0)
        recs.append({
            "segment":  "Sadık Müşteri",
            "color":    "#10B981",
            "icon":     "⭐",
            "count":    cnt,
            "revenue":  rev,
            "priority": "DÜŞÜK",
            "priority_color": "#10B981",
            "actions": [
                "VIP müşteri statüsü ve erken erişim kampanyaları sun",
                "Referral programına davet et (arkadaşını getir %10 kazan)",
                "Yeni ürün lansmanında öncelikli bildirim gönder",
            ],
            "expected_impact": f"Ortalama LTV'yi ₺{rev/max(cnt,1)*0.2:,.0f} artır",
        })

    # Yüksek Churn Alert
    if len(high_churn) > 0:
        total_custs = len(segments_df)
        churn_pct = round(len(high_churn) / total_custs * 100, 1)
        if churn_pct > 15:
            recs.insert(0, {
                "segment":  f"Churn Alarmı ({len(high_churn)} müşteri)",
                "color":    "#EF4444",
                "icon":     "🚨",
                "count":    len(high_churn),
                "revenue":  float(high_churn["total_revenue"].sum()),
                "priority": "ACİL",
                "priority_color": "#EF4444",
                "actions": [
                    f"Müşterilerin %{churn_pct:.0f}'ünün churn riski kritik seviyede",
                    "Acil retention kampanyası başlat",
                    "Segmentasyon sayfasında churn > 80 filtresi uygula",
                ],
                "expected_impact": "Kitlesel müşteri kaybını önle",
            })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# Yeni özellikler: İade Analizi, Zaman Dağılımı, Şehir, Stok Hızı
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_return_analysis(user_id: int, store_id: int | None = None) -> dict:
    """İade analizi — ürün bazlı iade oranı, aylık trend."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"has_data": False}

    total = len(df)
    iade = df[df["status"].str.contains("İade", na=False, case=False)]
    iade_rate = len(iade) / total * 100 if total > 0 else 0

    # Ürün bazlı iade oranı
    if "product_name" in df.columns and df["product_name"].str.strip().ne("").any():
        prod = df.groupby("product_name").agg(
            toplam=("status", "count"),
            iade=("status", lambda x: x.str.contains("İade", na=False, case=False).sum()),
        ).reset_index()
        prod["iade_oran"] = (prod["iade"] / prod["toplam"] * 100).round(1)
        prod = prod[prod["toplam"] >= 2].sort_values("iade_oran", ascending=False)
    else:
        prod = pd.DataFrame()

    # Aylık iade trendi
    df2 = df.copy()
    df2["ay"] = df2["order_date"].dt.to_period("M").astype(str)
    monthly = df2.groupby("ay").agg(
        toplam=("status", "count"),
        iade=("status", lambda x: x.str.contains("İade", na=False, case=False).sum()),
    ).reset_index()
    monthly["iade_oran"] = (monthly["iade"] / monthly["toplam"] * 100).round(1)

    return {
        "has_data": True,
        "total_orders": total,
        "total_returns": len(iade),
        "return_rate": round(iade_rate, 1),
        "by_product": prod,
        "monthly_trend": monthly,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def get_hourly_distribution(user_id: int, store_id: int | None = None) -> dict:
    """Sipariş saati ve haftanın günü dağılımı."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"has_data": False}

    has_hour = "order_hour" in df.columns and df["order_hour"].notna().sum() > 10

    if has_hour:
        hour_df = df[df["order_hour"].notna()].copy()
        hour_df["order_hour"] = hour_df["order_hour"].astype(int)
        hourly = hour_df.groupby("order_hour").size().reset_index(name="siparis")
        # Tüm 24 saati doldur
        hourly = pd.DataFrame({"order_hour": range(24)}).merge(hourly, on="order_hour", how="left").fillna(0)
        hourly["siparis"] = hourly["siparis"].astype(int)
    else:
        hourly = pd.DataFrame()

    # Haftanın günü (her zaman var — order_date'den)
    df2 = df.copy()
    df2["weekday"] = df2["order_date"].dt.weekday  # 0=Pzt, 6=Paz
    DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    weekday = df2.groupby("weekday").size().reset_index(name="siparis")
    weekday["gun"] = weekday["weekday"].apply(lambda x: DAYS[x])

    # Aylık sipariş trendi
    df2["ay"] = df2["order_date"].dt.to_period("M").astype(str)
    monthly_orders = df2.groupby("ay").size().reset_index(name="siparis")

    return {
        "has_data": True,
        "hourly": hourly,
        "has_hour_data": has_hour,
        "weekday": weekday,
        "monthly_orders": monthly_orders,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def get_city_distribution(user_id: int, store_id: int | None = None) -> dict:
    """Şehir bazlı sipariş ve gelir dağılımı."""
    df = _fetch_orders(user_id, store_id)
    if df.empty:
        return {"has_data": False}

    has_city = (
        "city" in df.columns
        and df["city"].str.strip().ne("").sum() > 5
    )
    if not has_city:
        return {"has_data": False, "no_city_data": True}

    city_df = df[df["city"].str.strip().ne("") & df["city"].notna()].copy()
    city_df["city"] = city_df["city"].str.strip()

    by_city = city_df.groupby("city").agg(
        siparis=("order_number", "count"),
        gelir=("total_amount", "sum"),
        musteri=("customer_identifier", "nunique"),
    ).reset_index().sort_values("siparis", ascending=False)

    by_city["gelir"] = by_city["gelir"].round(2)
    by_city["ort_siparis"] = (by_city["gelir"] / by_city["siparis"]).round(2)

    return {
        "has_data": True,
        "no_city_data": False,
        "by_city": by_city,
        "top_city": by_city.iloc[0]["city"] if not by_city.empty else "",
        "total_cities": len(by_city),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def get_stock_velocity(user_id: int, store_id: int | None = None) -> pd.DataFrame:
    """Ürün bazlı satış hızı (adet/gün). Stok riski hesabı için."""
    df = _fetch_orders(user_id, store_id)
    if df.empty or "product_name" not in df.columns:
        return pd.DataFrame()

    # Sadece teslim edilen siparişler
    delivered = df[df["status"].str.contains("Teslim", na=False, case=False)].copy()
    if delivered.empty:
        return pd.DataFrame()

    date_range = (delivered["order_date"].max() - delivered["order_date"].min()).days
    if date_range < 1:
        date_range = 1

    velocity = delivered.groupby("product_name").agg(
        toplam_adet=("quantity", "sum"),
        siparis_sayisi=("order_number", "count"),
        son_siparis=("order_date", "max"),
    ).reset_index()

    velocity["gunluk_satis"] = (velocity["toplam_adet"] / date_range).round(2)
    velocity["gunluk_satis"] = velocity["gunluk_satis"].clip(lower=0.01)
    velocity = velocity.sort_values("gunluk_satis", ascending=False)

    return velocity
