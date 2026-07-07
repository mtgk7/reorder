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

    # ── Müşteri Listesi (tıklanabilir) ───────────────────────────────────────
    _section("Müşteri Listesi — Churn Risk Skoru")
    st.markdown(
        """<div class="info-box" style="font-size:.82rem;">
        🔴 <b>70+</b> Yüksek Risk &nbsp;·&nbsp;
        🟡 <b>40-69</b> Orta Risk &nbsp;·&nbsp;
        🟢 <b>0-39</b> Düşük Risk &nbsp;·&nbsp;
        Bir müşteriye tıklayarak detayını görün.
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
        .sort_values("Churn Risk", ascending=False).head(200).reset_index(drop=True)
    )

    def _color_churn(val):
        if val >= 70:
            return "background-color:#FEE2E2;color:#991B1B;font-weight:700;"
        if val >= 40:
            return "background-color:#FEF9C3;color:#854D0E;font-weight:700;"
        return "background-color:#DCFCE7;color:#166534;font-weight:700;"

    display_fmt = display.copy()
    display_fmt["Toplam Harcama"] = display_fmt["Toplam Harcama"].apply(_fmt_tl)
    display_fmt["Ort. Sipariş"]   = display_fmt["Ort. Sipariş"].apply(_fmt_tl)
    try:
        styled = display_fmt.style.map(_color_churn, subset=["Churn Risk"])
    except AttributeError:
        styled = display_fmt.style.applymap(_color_churn, subset=["Churn Risk"])

    # Streamlit 1.35+ satır seçimi
    try:
        sel = st.dataframe(
            styled, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key="cust_table_sel",
        )
        selected_rows = sel.selection.rows if hasattr(sel, "selection") else []
    except Exception:
        st.dataframe(styled, use_container_width=True, hide_index=True)
        selected_rows = []

    # Seçili satırdan müşteri adını al
    selected_cust: str | None = None
    if selected_rows:
        idx = selected_rows[0]
        if idx < len(display):
            selected_cust = display.iloc[idx]["Müşteri"]

    # Selectbox fallback (satır tıklaması çalışmazsa)
    if not selected_cust:
        all_customers = sorted(segments_df["customer_identifier"].tolist())
        fb = st.selectbox("veya müşteri ara:", options=["— Seçin —"] + all_customers, key="cust_detail_fb")
        if fb and fb != "— Seçin —":
            selected_cust = fb

    # ── Aksiyon Önerileri — Segmentlere Göre ────────────────────────────────
    st.markdown('<hr style="border:none;border-top:1px solid rgba(242,122,26,.18);margin:1.6rem 0 1rem;">', unsafe_allow_html=True)
    _section("🎯 Aksiyon Önerileri — Segmentlere Göre")
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

    # ── Müşteri Detay Paneli ─────────────────────────────────────────────────
    if selected_cust:
        st.markdown('<hr style="border:none;border-top:1px solid rgba(242,122,26,.18);margin:1.6rem 0 1rem;">', unsafe_allow_html=True)
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
            action = detail.get("action", {})

            # Başlık
            city_txt = f" · 📍 {detail['city']}" if detail.get("city") else ""
            cadence_txt = f" · 🔁 Ort. her {detail['avg_cadence']} günde sipariş" if detail.get("avg_cadence") else ""
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:.8rem;">
                <span style="font-size:1.15rem;font-weight:800;color:#1e293b;">👤 {selected_cust}</span>
                <span style="background:{seg_color}22;color:{seg_color};padding:4px 12px;border-radius:20px;font-weight:700;font-size:.82rem;border:1px solid {seg_color}55;">{detail['segment']}</span>
                <span style="background:{churn_color}22;color:{churn_color};padding:4px 12px;border-radius:20px;font-weight:700;font-size:.82rem;border:1px solid {churn_color}55;">🔥 Churn: {churn}/100</span>
                <span style="font-size:.78rem;color:#6B7280;">{city_txt}{cadence_txt}</span>
                </div>""",
                unsafe_allow_html=True,
            )

            # KPI satırı
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Toplam Sipariş",  f"{detail['total_orders']}")
            d2.metric("Toplam Harcama",  _fmt_tl(detail["total_revenue"]))
            d3.metric("Ort. Sipariş",    _fmt_tl(detail["avg_order"]))
            d4.metric("Son Alışveriş",   f"{detail['days_since']} gün önce")
            d5.metric("İlk Alışveriş",   detail["first_date"])

            # Aksiyon kartı
            if action:
                st.markdown(
                    f"""<div style="background:{action['color']}12;border:1.5px solid {action['color']}40;
                    border-radius:12px;padding:14px 18px;margin:.8rem 0;">
                    <span style="font-size:1rem;font-weight:700;color:{action['color']};">{action['icon']} {action['title']}</span>
                    <p style="margin:.4rem 0 0;font-size:.84rem;color:#374151;">{action['text']}</p>
                    </div>""",
                    unsafe_allow_html=True,
                )

            # Grafikler
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
                    height=240, margin=dict(l=0, r=0, t=8, b=0),
                    xaxis=dict(title="", tickangle=-30, tickfont=dict(size=10)),
                    yaxis=dict(title="₺", tickprefix="₺", tickformat=",.0f"),
                    template="plotly_white",
                )
                st.plotly_chart(fig_ltv, use_container_width=True)

            with gc2:
                _section("📅 Aylık Harcama")
                fig_m = px.bar(
                    detail["monthly"], x="month_str", y="revenue",
                    color_discrete_sequence=["#3B82F6"],
                    labels={"month_str": "Ay", "revenue": "₺"},
                    template="plotly_white",
                )
                fig_m.update_layout(height=240, margin=dict(l=0, r=0, t=8, b=0))
                fig_m.update_xaxes(type="category")
                st.plotly_chart(fig_m, use_container_width=True)

            # Alt bölüm: en çok alınan ürünler + sipariş tablosu
            tp1, tp2 = st.columns([1, 2])
            with tp1:
                _section("🛒 En Çok Aldığı Ürünler")
                if not detail["top_products"].empty:
                    tp_fmt = detail["top_products"].copy()
                    tp_fmt["Toplam (₺)"] = tp_fmt["Toplam (₺)"].apply(_fmt_tl)
                    st.dataframe(tp_fmt, use_container_width=True, hide_index=True)
                else:
                    st.info("Ürün verisi yok.")

            with tp2:
                _section("📋 Tüm Siparişler")
                ord_cols = ["date_str", "order_number", "product_name", "quantity", "total_amount", "status"]
                available = [c for c in ord_cols if c in detail["orders"].columns]
                ord_tbl = detail["orders"][available].copy()
                ord_tbl.columns = ["Tarih", "Sipariş No", "Ürün", "Adet", "Tutar (₺)", "Durum"][:len(available)]
                if "Tutar (₺)" in ord_tbl.columns:
                    ord_tbl["Tutar (₺)"] = ord_tbl["Tutar (₺)"].apply(_fmt_tl)
                st.dataframe(ord_tbl.sort_values("Tarih", ascending=False), use_container_width=True, hide_index=True)
