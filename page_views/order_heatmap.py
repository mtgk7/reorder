"""page_views/order_heatmap.py — Sipariş Saati / Gün Haritası"""
from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from src.analytics import get_hourly_distribution
from src.ui_helpers import _header, _section, _kpi, _plan_gate


def run() -> None:
    if not _plan_gate("order_heatmap"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("⏰", "Sipariş Zaman Haritası", "En yoğun sipariş saatlerini ve günlerini keşfedin")

    result = get_hourly_distribution(user["id"], store_id)

    if not result.get("has_data"):
        st.markdown(
            """<div class="info-box">📂 Zaman haritası için sipariş verisi bulunamadı.
            Lütfen önce veri yükleyin.</div>""",
            unsafe_allow_html=True,
        )
        return

    # ── Haftanın Günü Dağılımı ────────────────────────────────────────────────
    _section("📅 Haftanın Günlerine Göre Sipariş Dağılımı")

    weekday = result.get("weekday", pd.DataFrame())
    if not weekday.empty:
        gun_order = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
        weekday["gun"] = pd.Categorical(weekday["gun"], categories=gun_order, ordered=True)
        weekday = weekday.sort_values("gun")

        total_orders = weekday["siparis"].sum()
        weekday["oran"] = (weekday["siparis"] / total_orders * 100).round(1)
        peak_day = weekday.loc[weekday["siparis"].idxmax(), "gun"]

        c1, c2, c3 = st.columns(3)
        with c1:
            _kpi("En Yoğun Gün", str(peak_day), icon="📅")
        with c2:
            _kpi("Toplam Sipariş", f"{total_orders:,}", icon="🛒")
        with c3:
            weekend = weekday[weekday["gun"].isin(["Cmt", "Paz"])]["siparis"].sum()
            weekday_total = weekday[~weekday["gun"].isin(["Cmt", "Paz"])]["siparis"].sum()
            _kpi(
                "Hafta Sonu Oranı",
                f"%{weekend / total_orders * 100:.1f}" if total_orders > 0 else "—",
                sub=f"{weekend:,} sipariş",
                icon="🗓️",
            )

        st.markdown("&nbsp;")

        colors = ["#F27A1A" if g == peak_day else "#CBD5E1" for g in weekday["gun"].tolist()]
        fig1 = go.Figure(go.Bar(
            x=weekday["gun"].tolist(),
            y=weekday["siparis"].tolist(),
            marker_color=colors,
            text=[f"%{o:.0f}" for o in weekday["oran"].tolist()],
            textposition="outside",
        ))
        fig1.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            yaxis=dict(title="Sipariş Sayısı", gridcolor="#F1F5F9"),
            xaxis=dict(title=""),
        )
        st.plotly_chart(fig1, use_container_width=True)

    # ── Saatlik Dağılım ───────────────────────────────────────────────────────
    hourly = result.get("hourly", pd.DataFrame())
    has_hour = result.get("has_hour_data", False)

    if has_hour and not hourly.empty:
        _section("🕐 Saate Göre Sipariş Dağılımı")

        peak_hour = int(hourly.loc[hourly["siparis"].idxmax(), "order_hour"])
        quiet_hour = int(hourly.loc[hourly["siparis"].idxmin(), "order_hour"])

        c1, c2 = st.columns(2)
        with c1:
            _kpi("En Yoğun Saat", f"{peak_hour:02d}:00 — {peak_hour+1:02d}:00", icon="🕐")
        with c2:
            _kpi("En Sakin Saat", f"{quiet_hour:02d}:00 — {quiet_hour+1:02d}:00", icon="😴")

        st.markdown("&nbsp;")

        hourly["label"] = hourly["order_hour"].apply(lambda h: f"{h:02d}:00")
        peak_h_series = hourly["siparis"].max()
        colors_h = ["#F27A1A" if s >= peak_h_series * 0.85 else "#3B82F6" if s >= peak_h_series * 0.6 else "#CBD5E1"
                    for s in hourly["siparis"]]

        fig2 = go.Figure(go.Bar(
            x=hourly["label"].tolist(),
            y=hourly["siparis"].tolist(),
            marker_color=colors_h,
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            yaxis=dict(title="Sipariş Sayısı", gridcolor="#F1F5F9"),
            xaxis=dict(title="Saat", tickangle=-45),
        )
        fig2.add_annotation(
            text="🔴 En Yoğun   🔵 Orta Yoğun   ⬜ Sakin",
            xref="paper", yref="paper",
            x=0.5, y=-0.18,
            showarrow=False,
            font=dict(size=11, color="#6B7280"),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # ── Heatmap ───────────────────────────────────────────────────────────
        # Heatmap için order_date + order_hour gerekli
        from src.analytics import _fetch_orders
        df = _fetch_orders(user["id"], store_id)
        if not df.empty and "order_hour" in df.columns and df["order_hour"].notna().sum() > 10:
            _section("🗓️ Gün × Saat Heatmap")
            hdf = df[df["order_hour"].notna()].copy()
            hdf["weekday"] = hdf["order_date"].dt.weekday
            hdf["order_hour"] = hdf["order_hour"].astype(int)
            hdf["gun"] = hdf["weekday"].map({0:"Pzt",1:"Sal",2:"Çar",3:"Per",4:"Cum",5:"Cmt",6:"Paz"})

            pivot = hdf.groupby(["gun", "order_hour"]).size().reset_index(name="siparis")
            pivot_table = pivot.pivot(index="gun", columns="order_hour", values="siparis").fillna(0)

            gun_order = ["Paz", "Cmt", "Cum", "Per", "Çar", "Sal", "Pzt"]
            pivot_table = pivot_table.reindex([g for g in gun_order if g in pivot_table.index])

            # Eksik sütunları doldur
            for h in range(24):
                if h not in pivot_table.columns:
                    pivot_table[h] = 0
            pivot_table = pivot_table[sorted(pivot_table.columns)]

            fig3 = px.imshow(
                pivot_table,
                labels=dict(x="Saat", y="Gün", color="Sipariş"),
                color_continuous_scale=["#F8FAFC", "#FDBA74", "#F27A1A", "#9A3412"],
                aspect="auto",
                template="plotly_white",
            )
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#1A1A2E",
                margin=dict(l=10, r=10, t=20, b=10),
                height=280,
                xaxis=dict(tickvals=list(range(24)), ticktext=[f"{h:02d}" for h in range(24)]),
            )
            st.plotly_chart(fig3, use_container_width=True)
    else:
        _section("🕐 Saate Göre Dağılım")
        st.markdown(
            """<div class="warn-box">⚠️ Sipariş saati verisi mevcut değil.
            Bu grafik için Trendyol API entegrasyonu ile senkronizasyon yapılması
            veya siparişlerde <b>sipariş_saati</b> sütununun bulunması gerekir.</div>""",
            unsafe_allow_html=True,
        )

    # ── Aylık Sipariş Trendi ──────────────────────────────────────────────────
    monthly_orders = result.get("monthly_orders", pd.DataFrame())
    if monthly_orders is not None and not monthly_orders.empty and len(monthly_orders) > 1:
        _section("📆 Aylık Sipariş Trendi")
        fig4 = px.line(
            monthly_orders,
            x="ay",
            y="siparis",
            markers=True,
            labels={"ay": "Ay", "siparis": "Sipariş Sayısı"},
            color_discrete_sequence=["#F27A1A"],
            template="plotly_white",
        )
        fig4.update_traces(line_width=2.5, marker_size=7)
        fig4.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=10, t=20, b=10),
            height=260,
            xaxis=dict(tickangle=-30),
            yaxis=dict(gridcolor="#F1F5F9"),
        )
        st.plotly_chart(fig4, use_container_width=True)
