"""page_views/campaign_roi.py — Kampanya ROI Analizi"""
from __future__ import annotations

from datetime import date, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from src.analytics import get_campaign_roi_analysis
from src.database import (
    save_campaign_roi_entry, get_campaign_roi_entries, delete_campaign_roi_entry,
)
from src.ui_helpers import _header, _section, _kpi, _fmt_tl, _plan_gate


def run() -> None:
    if not _plan_gate("campaign_roi"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("📣", "Kampanya ROI", "Kampanya dönemindeki gelir artışını ölçün")

    st.markdown(
        """<div class="info-box">
        Kampanya tarih aralığınızı ve indirim oranını girin. Sistem o dönemdeki sipariş cirosunu
        önceki aynı uzunluktaki dönemle karşılaştırır ve yatırım getirisini hesaplar.
        <br><b>ROI = (Kampanya Cirosu − Normal Ciro) / İndirim Tutarı × 100</b>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Kampanya Analiz Formu ─────────────────────────────────────────────────
    _section("🔍 Kampanya Analiz Et")

    with st.form("roi_form", border=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            camp_name  = st.text_input("Kampanya Adı", placeholder="örn: Yaz İndirimi 2026")
            start_date = st.date_input("Kampanya Başlangıç", value=date.today() - timedelta(days=30))
        with c2:
            discount_pct = st.number_input(
                "İndirim Oranı (%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5, format="%.1f"
            )
            end_date = st.date_input("Kampanya Bitiş", value=date.today())
        with c3:
            st.markdown("<br><br>", unsafe_allow_html=True)
            analyze_btn = st.form_submit_button("📊 Analiz Et", type="primary", use_container_width=True)
            save_btn    = st.form_submit_button("💾 Kaydet", use_container_width=True)

    roi_result = st.session_state.get("_roi_result")

    if analyze_btn or save_btn:
        if start_date >= end_date:
            st.error("Başlangıç tarihi bitiş tarihinden önce olmalı.")
        elif discount_pct <= 0:
            st.error("İndirim oranı sıfırdan büyük olmalı.")
        else:
            with st.spinner("Hesaplanıyor…"):
                roi_result = get_campaign_roi_analysis(
                    user["id"], store_id,
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                    discount_pct,
                )
            st.session_state["_roi_result"] = roi_result

            if save_btn and roi_result.get("has_data"):
                save_campaign_roi_entry(
                    user["id"], store_id,
                    camp_name or f"Kampanya {start_date}",
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                    discount_pct,
                )
                st.success(f"✅ '{camp_name}' kaydedildi!")

    # ── Sonuçları Göster ──────────────────────────────────────────────────────
    if roi_result and roi_result.get("has_data"):
        r = roi_result
        _section("📊 Analiz Sonuçları")

        # ROI rengi
        roi_color = "#10B981" if r["roi"] > 0 else "#EF4444"
        roi_icon  = "✅" if r["roi"] > 100 else ("🟡" if r["roi"] > 0 else "🔴")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _kpi("Kampanya Cirosu",  _fmt_tl(r["camp_rev"]),
                 f"{r['camp_orders']} sipariş", icon="📈")
        with c2:
            _kpi("Önceki Dönem Cirosu", _fmt_tl(r["prev_rev"]),
                 f"{r['prev_orders']} sipariş", icon="📉")
        with c3:
            delta_icon = "▲" if r["delta_pct"] >= 0 else "▼"
            delta_color_txt = "#10B981" if r["delta_pct"] >= 0 else "#EF4444"
            _kpi(
                "Ciro Farkı",
                f"{'+' if r['delta_pct'] >= 0 else ''}{_fmt_tl(r['delta_rev'])}",
                f"{delta_icon} %{r['delta_pct']:.1f}",
                icon="💰",
            )
        with c4:
            _kpi("ROI", f"%{r['roi']:.1f}", sub=f"İndirim Tutarı: {_fmt_tl(r['discount_amount'])}", icon=roi_icon)

        # ROI özet kutusu
        if r["roi"] > 100:
            box_bg, box_border, box_text = "#ECFDF5", "#6EE7B7", "#065F46"
            verdict = "Kampanya kârlıydı! Her ₺1 indirim için ₺{:.2f} ek ciro üretildi.".format(r["roi"] / 100 + 1)
        elif r["roi"] > 0:
            box_bg, box_border, box_text = "#FFFBEB", "#FCD34D", "#92400E"
            verdict = "Kampanya hafif pozitif etki yarattı. İndirim oranını optimize etmeyi deneyin."
        else:
            box_bg, box_border, box_text = "#FEF2F2", "#FECACA", "#991B1B"
            verdict = "Kampanya beklenen ciro artışını sağlamadı. Dönem, indirim oranı veya ürün seçimini gözden geçirin."

        st.markdown(
            f"""<div style="background:{box_bg};border:1px solid {box_border};border-radius:10px;
            padding:1rem 1.2rem;margin:1rem 0;">
            <b style="color:{box_text};font-size:.95rem;">{roi_icon} ROI %{r['roi']:.1f} — {verdict}</b>
            <div style="font-size:.8rem;color:{box_text};margin-top:.3rem;opacity:.85;">
            Kampanya: {r['camp_start']} → {r['camp_end']} &nbsp;|&nbsp;
            Kıyas Dönemi: {r['prev_start']} → {r['prev_end']} &nbsp;|&nbsp;
            İndirim Oranı: %{r['discount_pct']:.1f}
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # ── Günlük Trend Grafiği ──────────────────────────────────────────────
        if not r["daily_camp"].empty or not r["daily_prev"].empty:
            _section("📅 Günlük Ciro Karşılaştırması")

            combined = pd.concat([r["daily_camp"], r["daily_prev"]], ignore_index=True)
            if not combined.empty:
                fig = px.line(
                    combined,
                    x="gun_no",
                    y="gelir",
                    color="seri",
                    markers=True,
                    color_discrete_map={"Kampanya Dönemi": "#F27A1A", "Önceki Dönem": "#94A3B8"},
                    labels={"gun_no": "Gün", "gelir": "Günlük Ciro (₺)", "seri": ""},
                    template="plotly_white",
                )
                fig.update_traces(line_width=2.5, marker_size=6)
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#1A1A2E",
                    margin=dict(l=10, r=10, t=20, b=10),
                    height=300,
                    yaxis=dict(gridcolor="#F1F5F9"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig, use_container_width=True)

    elif roi_result and not roi_result.get("has_data"):
        st.warning("Seçilen dönem için sipariş verisi bulunamadı.")

    # ── Geçmiş Kampanyalar ────────────────────────────────────────────────────
    entries = get_campaign_roi_entries(user["id"], store_id)
    if entries:
        _section("📋 Kaydedilmiş Kampanyalar")
        hist_df = pd.DataFrame(entries)

        for _, row in hist_df.iterrows():
            # Her kampanyayı hızlıca hesapla
            quick = get_campaign_roi_analysis(
                user["id"], store_id,
                str(row["start_date"]), str(row["end_date"]), float(row["discount_pct"])
            )
            roi_val = quick.get("roi", 0.0) if quick.get("has_data") else 0.0
            icon    = "✅" if roi_val > 0 else "❌"

            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"""<div style="background:white;border:1px solid #E2E8F0;border-radius:10px;
                    padding:.7rem 1rem;margin:.25rem 0;box-shadow:0 1px 4px rgba(0,0,0,.05);">
                    {icon} <b style="color:#1A1A2E;">{row['campaign_name']}</b>
                    <span style="color:#6B7280;font-size:.8rem;margin-left:.5rem;">
                    {row['start_date']} — {row['end_date']} | %{row['discount_pct']:.1f} indirim</span>
                    {'<span style="margin-left:.7rem;font-weight:700;color:' + ('#10B981' if roi_val > 0 else '#EF4444') + ';">ROI: %' + f'{roi_val:.1f}' + '</span>' if quick.get("has_data") else ''}
                    </div>""",
                    unsafe_allow_html=True,
                )
            with col2:
                if st.button("🗑️", key=f"del_roi_{row['id']}", help="Sil"):
                    delete_campaign_roi_entry(int(row["id"]), user["id"])
                    st.session_state.pop("_roi_result", None)
                    st.rerun()
