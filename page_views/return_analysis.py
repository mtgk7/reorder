"""page_views/return_analysis.py — İade Analizi"""
from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src.analytics import get_return_analysis
from src.ui_helpers import _header, _section, _kpi, _fmt_tl, _plan_gate


def run() -> None:
    if not _plan_gate("return_analysis"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("🔄", "İade Analizi", "İade oranı yüksek ürünleri tespit edin")

    result = get_return_analysis(user["id"], store_id)

    if not result.get("has_data"):
        st.markdown(
            """<div class="info-box">📂 İade analizi için sipariş verisi bulunamadı.
            Veri Yükle sayfasından Trendyol sipariş raporunuzu yükleyin.
            Siparişlerdeki <b>durum</b> sütununda "İade", "Returned", "iade" gibi
            değerler varsa sistem otomatik olarak analiz eder.</div>""",
            unsafe_allow_html=True,
        )
        return

    total    = result["total_orders"]
    ret_cnt  = result["total_returns"]
    ret_rate = result["return_rate"]

    # ── KPI'lar ───────────────────────────────────────────────────────────────
    _section("📊 İade Özeti")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi("Toplam Sipariş", f"{total:,}", icon="🛒")
    with c2:
        _kpi("Toplam İade", f"{ret_cnt:,}", icon="🔄")
    with c3:
        oran_color = "#EF4444" if ret_rate > 10 else ("#F59E0B" if ret_rate > 5 else "#10B981")
        _kpi("İade Oranı", f"%{ret_rate}", sub=("Yüksek ⚠️" if ret_rate > 10 else "Normal"), icon="📊")
    with c4:
        _kpi("Tamamlanan Sipariş", f"{total - ret_cnt:,}", icon="✅")

    if ret_rate > 10:
        st.markdown(
            f"""<div style="background:#FEF2F2;border:1px solid #FECACA;border-left:4px solid #EF4444;
            border-radius:8px;padding:.8rem 1rem;margin:.5rem 0;">
            ⚠️ <b style="color:#991B1B;">Yüksek İade Oranı!</b>
            <span style="color:#7F1D1D;font-size:.88rem;">
            İade oranınız %{ret_rate} ile endüstri ortalamasının üzerinde.
            Ürün kalitesi, boyut/renk uyumu veya kargo hasarını kontrol edin.</span>
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Ürün Bazlı İade ───────────────────────────────────────────────────────
    prod_df = result.get("by_product")
    if prod_df is not None and not prod_df.empty:
        _section("🛍️ Ürün Bazlı İade Oranı (En Yüksek 15)")
        top15 = prod_df.head(15).copy()
        top15["ürün"] = top15["product_name"].str[:40]

        fig = px.bar(
            top15,
            x="iade_oran",
            y="ürün",
            orientation="h",
            color="iade_oran",
            color_continuous_scale=["#10B981", "#F59E0B", "#EF4444"],
            labels={"iade_oran": "İade Oranı (%)", "ürün": ""},
            template="plotly_white",
            text="iade_oran",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            coloraxis_showscale=False,
            margin=dict(l=10, r=40, t=10, b=10),
            height=max(300, len(top15) * 38),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tablo
        with st.expander("📋 Detaylı Tablo"):
            display = top15[["product_name", "toplam", "iade", "iade_oran"]].copy()
            display.columns = ["Ürün Adı", "Toplam Sipariş", "İade Adedi", "İade Oranı (%)"]
            st.dataframe(display, use_container_width=True, hide_index=True)

    # ── Aylık İade Trendi ─────────────────────────────────────────────────────
    monthly = result.get("monthly_trend")
    if monthly is not None and not monthly.empty and len(monthly) > 1:
        _section("📅 Aylık İade Trendi")

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=monthly["ay"],
            y=monthly["toplam"],
            name="Toplam Sipariş",
            marker_color="#E2E8F0",
        ))
        fig2.add_trace(go.Bar(
            x=monthly["ay"],
            y=monthly["iade"],
            name="İade",
            marker_color="#EF4444",
        ))
        fig2.add_trace(go.Scatter(
            x=monthly["ay"],
            y=monthly["iade_oran"],
            name="İade Oranı (%)",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#F59E0B", width=2),
            marker=dict(size=6),
        ))
        fig2.update_layout(
            barmode="group",
            yaxis2=dict(
                title="İade Oranı (%)",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=50, t=20, b=10),
            height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig2, use_container_width=True)

    if ret_cnt == 0:
        st.markdown(
            """<div class="success-box">✅ <b>Harika!</b> Sipariş verilerinde henüz iade kaydı bulunamadı.
            Verilerinizde "İade", "Returned", "iade" gibi durum değerleri varsa otomatik tespit edilir.</div>""",
            unsafe_allow_html=True,
        )
