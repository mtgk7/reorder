"""page_views/seller_scores.py — Satıcı Skoru Takibi"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import pandas as pd

from src.database import save_seller_score, get_seller_scores, delete_seller_score
from src.ui_helpers import _header, _section, _kpi, _plan_gate


_SCORE_COLORS = {
    "excellent": "#10B981",   # >= 4.5
    "good":      "#3B82F6",   # >= 4.0
    "average":   "#F59E0B",   # >= 3.5
    "poor":      "#EF4444",   # < 3.5
}


def _score_color(val: float | None) -> str:
    if val is None:
        return "#9CA3AF"
    if val >= 4.5:
        return _SCORE_COLORS["excellent"]
    if val >= 4.0:
        return _SCORE_COLORS["good"]
    if val >= 3.5:
        return _SCORE_COLORS["average"]
    return _SCORE_COLORS["poor"]


def _score_label(val: float | None) -> str:
    if val is None:
        return "—"
    if val >= 4.5:
        return "Mükemmel ⭐"
    if val >= 4.0:
        return "İyi 👍"
    if val >= 3.5:
        return "Ortalama ⚠️"
    return "Düşük 🔴"


def run() -> None:
    if not _plan_gate("seller_scores"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("⭐", "Satıcı Skoru Takibi", "Trendyol satıcı paneli puanlarınızı takip edin")

    st.markdown(
        """<div class="info-box">
        Trendyol Satıcı Paneli'nden kargo, iade ve müşteri memnuniyeti puanlarınızı manuel olarak girin.
        Sistem tarihsel trend grafiği oluşturur ve hedef belirlemenize yardımcı olur.
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Yeni Puan Girişi ──────────────────────────────────────────────────────
    _section("➕ Yeni Puan Girişi")

    with st.form("score_form", border=False):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            score_date = st.date_input("Tarih", value=date.today())
        with c2:
            cargo_score = st.number_input(
                "Kargo Puanı (1-5)", min_value=1.0, max_value=5.0, value=4.5, step=0.1, format="%.1f"
            )
        with c3:
            return_score = st.number_input(
                "İade Puanı (1-5)", min_value=1.0, max_value=5.0, value=4.5, step=0.1, format="%.1f"
            )
        with c4:
            satisfaction_score = st.number_input(
                "Memnuniyet Puanı (1-5)", min_value=1.0, max_value=5.0, value=4.5, step=0.1, format="%.1f"
            )

        note = st.text_input("Not (Opsiyonel)", placeholder="örn: Kargoda gecikme yaşandı")
        submitted = st.form_submit_button("Kaydet", type="primary", use_container_width=True)

    if submitted:
        save_seller_score(
            user["id"], store_id,
            score_date.strftime("%Y-%m-%d"),
            float(cargo_score), float(return_score), float(satisfaction_score),
            note or "",
        )
        st.success(f"✅ {score_date} tarihi için puanlar kaydedildi!")
        st.rerun()

    # ── Mevcut Skorlar ────────────────────────────────────────────────────────
    scores = get_seller_scores(user["id"], store_id)

    if not scores:
        st.markdown(
            """<div class="info-box">📭 Henüz satıcı puanı girilmedi.
            Yukarıdaki formu kullanarak Trendyol Satıcı Paneli'nden puanlarınızı düzenli aralıklarla girin.</div>""",
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(scores)
    df["score_date"] = pd.to_datetime(df["score_date"])
    df = df.sort_values("score_date")

    # ── Son Puan KPI ──────────────────────────────────────────────────────────
    _section("📊 Son Puan Durumu")
    latest = df.iloc[-1]

    c_score = float(latest.get("cargo_score") or 0)
    r_score = float(latest.get("return_score") or 0)
    s_score = float(latest.get("satisfaction_score") or 0)
    avg_score = round((c_score + r_score + s_score) / 3, 2) if (c_score and r_score and s_score) else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi("Genel Ortalama", f"{avg_score:.2f}/5",
             _score_label(avg_score), icon="⭐")
    with c2:
        _kpi("Kargo Puanı", f"{c_score:.1f}/5",
             _score_label(c_score), icon="🚚")
    with c3:
        _kpi("İade Puanı", f"{r_score:.1f}/5",
             _score_label(r_score), icon="🔄")
    with c4:
        _kpi("Memnuniyet", f"{s_score:.1f}/5",
             _score_label(s_score), icon="😊")

    # ── Hedef Belirleme ───────────────────────────────────────────────────────
    _section("🎯 Hedef Belirleme")

    # Varsayılan değerleri session_state'ten oku
    target_cargo  = st.session_state.get("_sc_target_cargo", 4.8)
    target_return = st.session_state.get("_sc_target_return", 4.8)
    target_sat    = st.session_state.get("_sc_target_sat", 4.8)

    with st.expander("Hedef puanları ayarla (Opsiyonel)", expanded=False):
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            target_cargo = st.slider("Kargo Hedefi", 3.0, 5.0, float(target_cargo), 0.1)
        with tc2:
            target_return = st.slider("İade Hedefi", 3.0, 5.0, float(target_return), 0.1)
        with tc3:
            target_sat = st.slider("Memnuniyet Hedefi", 3.0, 5.0, float(target_sat), 0.1)
        st.session_state["_sc_target_cargo"]  = target_cargo
        st.session_state["_sc_target_return"] = target_return
        st.session_state["_sc_target_sat"]    = target_sat

    # ── Trend Grafiği ─────────────────────────────────────────────────────────
    _section("📈 Puan Trendi")

    df["tarih_str"] = df["score_date"].dt.strftime("%d.%m.%Y")

    fig = go.Figure()

    for col, label, color in [
        ("cargo_score",        "Kargo",       "#F27A1A"),
        ("return_score",       "İade",        "#3B82F6"),
        ("satisfaction_score", "Memnuniyet",  "#10B981"),
    ]:
        if col in df.columns and df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=df["tarih_str"],
                y=df[col].astype(float),
                name=label,
                mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=7),
            ))

    # Hedef çizgileri
    for target, color, name in [
        (target_cargo,  "#F27A1A", "Hedef Kargo"),
        (target_return, "#3B82F6", "Hedef İade"),
        (target_sat,    "#10B981", "Hedef Memnuniyet"),
    ]:
        fig.add_hline(
            y=target, line_dash="dot", line_color=color,
            opacity=0.4,
            annotation_text=f"{name}: {target:.1f}",
            annotation_position="right",
        )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#1A1A2E",
        margin=dict(l=10, r=80, t=20, b=10),
        height=360,
        yaxis=dict(range=[0, 5.2], gridcolor="#F1F5F9", title="Puan (1-5)"),
        xaxis=dict(tickangle=-30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Geçmiş Tablo ──────────────────────────────────────────────────────────
    _section("📋 Geçmiş Kayıtlar")

    disp = df[["tarih_str", "cargo_score", "return_score", "satisfaction_score", "note"]].copy()
    disp.columns = ["Tarih", "Kargo", "İade", "Memnuniyet", "Not"]
    disp = disp.sort_values("Tarih", ascending=False).reset_index(drop=True)
    st.dataframe(disp, use_container_width=True, hide_index=True)

    # ── Sil ───────────────────────────────────────────────────────────────────
    _section("🗑️ Kayıt Sil")
    df_rev = df.sort_values("score_date", ascending=False)
    opts = {
        f"{r['tarih_str']} (ID:{r['id']})": int(r["id"])
        for _, r in df_rev.iterrows()
    }
    to_del = st.selectbox("Silinecek kayıt", options=list(opts.keys()), label_visibility="collapsed")
    if st.button("🗑️ Sil", key="del_score", type="secondary"):
        delete_seller_score(opts[to_del], user["id"])
        st.success("Kayıt silindi.")
        st.rerun()
