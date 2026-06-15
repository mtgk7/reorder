"""pages/segments.py — Müşteri Segmentleri sayfası"""
from __future__ import annotations
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src.analytics import get_summary_metrics, get_customer_segments, get_customer_detail, get_segment_recommendations
from src.ui_helpers import _fmt_tl, _header, _section, _plan_gate


def run() -> None:
    if not _plan_gate("segments"):
        return
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("👥", "Müşteri Segmentleri", "RFM tabanlı otomatik segmentasyon")

    m = get_summary_metrics(user["id"], store_id)
    if not m["has_data"]:
        st.info("Veri bulunamadı.")
        return

    segments_df = get_customer_segments(user["id"], store_id)
    if segments_df.empty:
        st.info("Yeterli veri yok.")
        return

    seg_summary = (
        segments_df.groupby("segment")
        .agg(musteri_sayisi=("customer_identifier", "count"), toplam_gelir=("total_revenue", "sum"))
        .reset_index()
        .sort_values("musteri_sayisi", ascending=False)
    )

    c1, c2 = st.columns(2)
    colors = {
        "Sadık Müşteri": "#10B981", "Gelişen Müşteri": "#3B82F6",
        "Yeni Müşteri": "#F59E0B", "Risk Altında": "#EF4444",
        "Tek Alışveriş": "#9CA3AF", "Kaybolma Riski": "#6B7280",
    }

    with c1:
        _section("Segment Dağılımı")
        fig = px.pie(
            seg_summary, names="segment", values="musteri_sayisi",
            color="segment", color_discrete_map=colors, hole=0.45, template="plotly_white",
        )
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        _section("Gelir Katkısı")
        fig2 = px.bar(
            seg_summary, x="segment", y="toplam_gelir", color="segment",
            color_discrete_map=colors, labels={"segment": "", "toplam_gelir": "Gelir (₺)"},
            template="plotly_white",
        )
        fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    _section("Segment Detay Tablosu")
    table = seg_summary.copy()
    table["toplam_gelir"] = table["toplam_gelir"].apply(_fmt_tl)
    table.columns = ["Segment", "Müşteri Sayısı", "Toplam Gelir"]
    st.dataframe(table, use_container_width=True, hide_index=True)

    _section("Müşteri Listesi — Churn Risk Skoru (İlk 100)")
    st.markdown(
        """<div class="info-box" style="font-size:.82rem;">
        🔴 <b>70+</b> Yüksek Risk &nbsp;·&nbsp;
        🟡 <b>40-69</b> Orta Risk &nbsp;·&nbsp;
        🟢 <b>0-39</b> Düşük Risk &nbsp;·&nbsp;
        Skor yükseldikçe müşteri kaybetme ihtimali artar.
        </div>""",
        unsafe_allow_html=True,
    )

    show_cols = ["customer_identifier", "segment", "churn_score", "total_orders", "total_revenue", "avg_order_value", "days_since_last"]
    col_rename = {
        "customer_identifier": "Müşteri", "segment": "Segment", "churn_score": "Churn Risk",
        "total_orders": "Sipariş", "total_revenue": "Toplam Harcama",
        "avg_order_value": "Ort. Sipariş", "days_since_last": "Son Alış. (Gün)",
    }
    display = (
        segments_df[show_cols].rename(columns=col_rename)
        .sort_values("Churn Risk", ascending=False).head(100).reset_index(drop=True)
    )
    display["Toplam Harcama"] = display["Toplam Harcama"].apply(_fmt_tl)
    display["Ort. Sipariş"]   = display["Ort. Sipariş"].apply(_fmt_tl)

    def _color_churn(val):
        if val >= 70:
            return "background-color:#FEE2E2;color:#991B1B;font-weight:700;"
        if val >= 40:
            return "background-color:#FEF9C3;color:#854D0E;font-weight:700;"
        return "background-color:#DCFCE7;color:#166534;font-weight:700;"

    try:
        styled = display.style.map(_color_churn, subset=["Churn Risk"])
    except AttributeError:
        styled = display.style.applymap(_color_churn, subset=["Churn Risk"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown('<hr style="border:none;border-top:1px solid rgba(242,122,26,.18);margin:1.6rem 0 1rem;">', unsafe_allow_html=True)
    _section("🎯 Aksiyon Önerileri — Segmentlere Göre")
    st.markdown(
        """<div class="info-box" style="font-size:.82rem;">
        Her segment için yapay zeka destekli öncelikli aksiyon listesi.
        En kritik segmentler önce gösterilir.
        </div>""",
        unsafe_allow_html=True,
    )
    try:
        recs = get_segment_recommendations(user["id"], store_id)
        if recs:
            for rec in recs:
                with st.expander(
                    f"{rec['icon']} {rec['segment']} — {rec['count']} müşteri | [{rec['priority']}]",
                    expanded=(rec.get("priority") in ("ACİL", "YÜKSEK")),
                ):
                    ra1, ra2 = st.columns([2, 1])
                    with ra1:
                        st.markdown("**Önerilen Aksiyonlar:**")
                        for action in rec["actions"]:
                            st.markdown(f"- {action}")
                    with ra2:
                        st.markdown(
                            f"""<div style="background:{rec['color']}15;border:1px solid {rec['color']}40;
                            border-radius:10px;padding:14px;text-align:center;">
                            <div style="font-size:.72rem;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem;">Beklenen Etki</div>
                            <div style="font-size:.88rem;font-weight:700;color:{rec['color']};">{rec['expected_impact']}</div>
                            <div style="font-size:.72rem;color:#9CA3AF;margin-top:.4rem;">Toplam Gelir: {_fmt_tl(rec.get('revenue', 0))}</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )
        else:
            st.info("Yeterli müşteri segmenti bulunamadı.")
    except Exception:
        pass

    st.markdown("&nbsp;")
    _section("👤 Müşteri Detay")
    all_customers = sorted(segments_df["customer_identifier"].tolist())
    selected_cust = st.selectbox("Müşteri seç", options=["— Seçin —"] + all_customers, key="cust_detail_select")

    if selected_cust and selected_cust != "— Seçin —":
        detail = get_customer_detail(user["id"], selected_cust, store_id)
        if detail:
            churn = detail["churn_score"]
            churn_color = "#EF4444" if churn >= 70 else ("#F59E0B" if churn >= 40 else "#10B981")
            seg_colors = {
                "Sadık Müşteri": "#10B981", "Gelişen Müşteri": "#3B82F6",
                "Yeni Müşteri": "#F59E0B", "Risk Altında": "#EF4444",
                "Tek Alışveriş": "#9CA3AF", "Kaybolma Riski": "#6B7280",
            }
            seg_color = seg_colors.get(detail["segment"], "#6B7280")

            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Toplam Sipariş",  f"{detail['total_orders']}")
            d2.metric("Toplam Harcama",  _fmt_tl(detail["total_revenue"]))
            d3.metric("Ort. Sipariş",    _fmt_tl(detail["avg_order"]))
            d4.metric("Son Alışveriş",   f"{detail['days_since']} gün önce")
            d5.metric("İlk Alışveriş",   detail["first_date"])

            st.markdown(
                f"""<div style="margin:.6rem 0;">
                <span style="background:{seg_color}22;color:{seg_color};padding:5px 14px;border-radius:20px;font-weight:700;font-size:.88rem;border:1px solid {seg_color}55;">
                    {detail['segment']}
                </span>
                &nbsp;
                <span style="background:{churn_color}22;color:{churn_color};padding:5px 14px;border-radius:20px;font-weight:700;font-size:.88rem;border:1px solid {churn_color}55;">
                    🔥 Churn Risk: {churn}/100
                </span>
                </div>""",
                unsafe_allow_html=True,
            )

            gc1, gc2 = st.columns(2)
            with gc1:
                _section("📈 Kümülatif LTV Trendi")
                fig_ltv = go.Figure(go.Scatter(
                    x=detail["orders"]["date_str"], y=detail["orders"]["cumulative_ltv"],
                    mode="lines+markers",
                    line=dict(color="#F27A1A", width=2.5),
                    marker=dict(size=7, color="#F27A1A"),
                    fill="tozeroy", fillcolor="rgba(242,122,26,.1)",
                    hovertemplate="<b>%{x}</b><br>Kümülatif: ₺%{y:,.2f}<extra></extra>",
                ))
                fig_ltv.update_layout(
                    height=260, margin=dict(l=0, r=0, t=8, b=0),
                    xaxis=dict(title="", tickangle=-30, tickfont=dict(size=10)),
                    yaxis=dict(title="₺", tickprefix="₺", tickformat=",.0f"),
                    template="plotly_white",
                )
                st.plotly_chart(fig_ltv, use_container_width=True)

            with gc2:
                _section("📅 Aylık Harcama")
                import plotly.express as _px
                fig_m = _px.bar(
                    detail["monthly"], x="month_str", y="revenue",
                    color_discrete_sequence=["#3B82F6"],
                    labels={"month_str": "Ay", "revenue": "₺"},
                    template="plotly_white",
                )
                fig_m.update_layout(height=260, margin=dict(l=0, r=0, t=8, b=0))
                fig_m.update_xaxes(type="category")
                st.plotly_chart(fig_m, use_container_width=True)

            _section("📋 Tüm Siparişler")
            ord_tbl = detail["orders"][["date_str", "order_number", "product_name", "quantity", "total_amount", "status"]].copy()
            ord_tbl.columns = ["Tarih", "Sipariş No", "Ürün", "Adet", "Tutar (₺)", "Durum"]
            ord_tbl["Tutar (₺)"] = ord_tbl["Tutar (₺)"].apply(_fmt_tl)
            st.dataframe(ord_tbl.sort_values("Tarih", ascending=False), use_container_width=True, hide_index=True)
