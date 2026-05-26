"""
analytics.py — Retention, Cohort analizi ve LTV hesaplama motoru.
PostgreSQL ve SQLite ile uyumludur.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
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


def _fetch_orders(user_id: int, conn=None) -> pd.DataFrame:
    """Kullanıcıya ait tüm siparişleri DataFrame olarak döndürür."""
    close = conn is None
    if conn is None:
        conn = get_connection()

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

def get_summary_metrics(user_id: int) -> dict:
    """
    Temel dashboard metriklerini hesaplar.

    Anahtarlar:
        has_data, total_orders, unique_customers, total_revenue,
        avg_order_value, repeat_customers, repeat_rate,
        avg_ltv, top_customer_revenue
    """
    df = _fetch_orders(user_id)

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

def get_cohort_retention(user_id: int) -> tuple[pd.DataFrame, pd.Series]:
    """
    Aylık cohort retention matrisi hesaplar.

    Dönüş:
        (retention_pct_df, cohort_sizes)
        retention_pct_df  — satır=cohort ayı, sütun=Ay 0,1,2… → değer = %
        cohort_sizes      — her cohort'taki benzersiz müşteri sayısı
    """
    df = _fetch_orders(user_id)
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

def get_monthly_trend(user_id: int) -> pd.DataFrame:
    """
    Her ay için sipariş sayısı, gelir ve benzersiz müşteri sayısını döndürür.
    """
    df = _fetch_orders(user_id)
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


def get_new_vs_returning(user_id: int) -> pd.DataFrame:
    """
    Aylık yeni / geri dönen müşteri ayrımı.
    """
    df = _fetch_orders(user_id)
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

def get_customer_segments(user_id: int) -> pd.DataFrame:
    """
    Her müşteri için basit RFM-tabanlı segment atar.

    Segmentler:
        Sadık Müşteri | Gelişen Müşteri | Yeni Müşteri |
        Risk Altında  | Tek Alışveriş   | Kaybolma Riski
    """
    df = _fetch_orders(user_id)
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
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# LTV Dağılımı
# ─────────────────────────────────────────────────────────────────────────────

def get_ltv_distribution(user_id: int) -> pd.DataFrame:
    """Müşteri başı toplam harcama dağılımını döndürür."""
    df = _fetch_orders(user_id)
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


def get_top_customers(user_id: int, n: int = 10) -> pd.DataFrame:
    """En yüksek LTV'li N müşteriyi döndürür."""
    df = get_ltv_distribution(user_id)
    if df.empty:
        return pd.DataFrame()
    return df.head(n).reset_index(drop=True)
