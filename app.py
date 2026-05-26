"""
app.py — ReOrder Streamlit Web Arayüzü (Ana Giriş Noktası)
Çalıştırmak için: streamlit run app.py
"""
from __future__ import annotations

# Lokal geliştirme için .env dosyasını yükle (production'da etkisizdir)
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

from src.database import init_db as _init_db
from src.auth import login_user, register_user, update_store_name, change_password
from src.parser import parse_trendyol_file, import_to_db, generate_sample_orders
from src.report import generate_report
from src.trendyol_api import (
    save_credentials, load_credentials, sync_orders,
    TrendyolClient, TrendyolAPIError,
)
from src.analytics import (
    get_summary_metrics,
    get_cohort_retention,
    get_monthly_trend,
    get_new_vs_returning,
    get_customer_segments,
    get_ltv_distribution,
    get_top_customers,
)

# ─────────────────────────────────────────────────────────────────────────────
# Başlatma — cache_resource ile yalnızca bir kez çalışır (rerun'larda atlanır)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def _init_db_once():
    _init_db()

_init_db_once()

st.set_page_config(
    page_title="ReOrder — Trendyol Retention",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit UI elementlerini gizle
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    [class*="viewerBadge"] {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

# Tema & CSS
st.markdown(
    """
<style>
    /* ── Genel ── */
    [data-testid="stAppViewContainer"] { background: #F8FAFC; }
    [data-testid="stSidebar"] {
        background: linear-gradient(160deg, #1A1A2E 0%, #16213E 100%);
    }
    [data-testid="stSidebar"] * { color: #E2E8F0 !important; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    /* ── Başlık şeridi ── */
    .app-header {
        background: linear-gradient(135deg, #F27A1A 0%, #D4621A 100%);
        border-radius: 12px;
        padding: 1.2rem 1.6rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }
    .app-header h1 { color: white !important; margin: 0; font-size: 1.6rem; }
    .app-header p  { color: rgba(255,255,255,.85) !important; margin: 0; font-size: .9rem; }

    /* ── KPI Kartları ── */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        border-left: 4px solid #F27A1A;
        box-shadow: 0 1px 6px rgba(0,0,0,.06);
        height: 100%;
    }
    .kpi-label { font-size: .78rem; font-weight: 600; color: #6B7280;
                 text-transform: uppercase; letter-spacing: .05em; margin-bottom: .3rem; }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #1A1A2E; }
    .kpi-sub   { font-size: .8rem; color: #9CA3AF; margin-top: .15rem; }

    /* ── Bölüm başlığı ── */
    .section-title {
        font-size: 1rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 1.5rem 0 .6rem 0;
        padding-bottom: .3rem;
        border-bottom: 2px solid #F27A1A;
        display: inline-block;
    }

    /* ── Bildirim kutuları ── */
    .info-box {
        background: #EFF6FF; border: 1px solid #BFDBFE;
        border-radius: 8px; padding: 1rem; margin: .5rem 0;
        color: #1E40AF; font-size: .88rem;
    }
    .warn-box {
        background: #FFFBEB; border: 1px solid #FCD34D;
        border-radius: 8px; padding: 1rem; margin: .5rem 0;
        color: #92400E; font-size: .88rem;
    }
    .success-box {
        background: #ECFDF5; border: 1px solid #6EE7B7;
        border-radius: 8px; padding: 1rem; margin: .5rem 0;
        color: #065F46; font-size: .88rem;
    }

    /* ── Buton ── */
    .stButton > button {
        background: #F27A1A !important; color: white !important;
        border: none !important; border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover { background: #D4621A !important; }

    /* ── Cohort tablosu ── */
    .cohort-table td, .cohort-table th {
        font-size: .78rem; padding: .3rem .5rem;
    }

    /* ── Sidebar nav düğmeleri ── */
    div[data-testid="stSidebar"] .stButton > button {
        background: rgba(255,255,255,.08) !important;
        border: 1px solid rgba(255,255,255,.12) !important;
        color: #E2E8F0 !important;
        width: 100%; text-align: left; margin-bottom: .2rem;
        border-radius: 8px !important;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(242,122,26,.25) !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    defaults = {"user": None, "page": "dashboard", "upload_result": None}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_tl(val: float) -> str:
    return f"₺{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _kpi(label: str, value: str, sub: str = "") -> None:
    st.markdown(
        f"""<div class="kpi-card">
               <div class="kpi-label">{label}</div>
               <div class="kpi-value">{value}</div>
               <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _header(icon: str, title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""<div class="app-header">
               <span style="font-size:2rem;">{icon}</span>
               <div><h1>{title}</h1><p>{subtitle}</p></div>
            </div>""",
        unsafe_allow_html=True,
    )


def _section(title: str) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def _go(page: str) -> None:
    st.session_state.page = page
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Giriş / Kayıt
# ─────────────────────────────────────────────────────────────────────────────
def show_auth() -> None:

    # ── Fütüristik Login Page CSS ─────────────────────────────────────────────
    st.markdown("""
    <style>
    /* ══════════════════════════════════════════════════
       1. ARKA PLAN — petrol mavisi / koyu camgöbeği
    ══════════════════════════════════════════════════ */
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section[data-testid="stMain"] > div:first-child {
        background: linear-gradient(145deg,
            #0a2533 0%,
            #0d3a4b 40%,
            #134e5e 75%,
            #0a2e3d 100%) !important;
        min-height: 100vh !important;
    }
    body, html { overflow-x: hidden; }
    [data-testid="stSidebar"]   { display: none !important; }
    [data-testid="stHeader"]    { background: transparent !important; }
    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 5rem !important;
        background: transparent !important;
        max-width: 100% !important;
    }

    /* Dekoratif arka plan ışımaları */
    [data-testid="stAppViewContainer"]::before {
        content:""; position:fixed;
        top:-15%; left:-5%; width:45%; height:45%;
        background: radial-gradient(ellipse, rgba(242,133,0,.09) 0%, transparent 65%);
        pointer-events:none; z-index:0;
    }
    [data-testid="stAppViewContainer"]::after {
        content:""; position:fixed;
        bottom:-10%; right:-5%; width:40%; height:40%;
        background: radial-gradient(ellipse, rgba(19,78,94,.35) 0%, transparent 65%);
        pointer-events:none; z-index:0;
    }

    /* ══════════════════════════════════════════════════
       2. GLASSMORPHIC KART (orta kolon)
    ══════════════════════════════════════════════════ */
    [data-testid="stHorizontalBlock"] >
    [data-testid="stColumn"]:nth-child(2) >
    [data-testid="stVerticalBlock"] {
        background:        rgba(40, 60, 75, 0.65) !important;
        backdrop-filter:   blur(10px) saturate(120%) !important;
        -webkit-backdrop-filter: blur(10px) saturate(120%) !important;
        border-radius:     16px !important;
        border:            1px solid rgba(242, 133, 0, 0.4) !important;
        box-shadow:
            0 0 20px  rgba(242, 133, 0, 0.20),
            0 8px 32px rgba(0, 0, 0, 0.45) !important;
        padding: 2rem 1.8rem !important;
        position: relative; z-index: 1;
    }

    /* ══════════════════════════════════════════════════
       3. SEKMELER — aktif: turuncu dolgu; pasif: silik gri
    ══════════════════════════════════════════════════ */
    [data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid rgba(242,133,0,.25) !important;
        gap: 6px !important;
        padding-bottom: 0 !important;
    }
    /* Tüm sekmeler — pasif */
    [data-testid="stTabs"] [role="tab"] {
        background:    rgba(255,255,255,.06) !important;
        color:         rgba(255,255,255,.38) !important;
        font-weight:   600 !important;
        font-size:     .85rem !important;
        border-radius: 8px 8px 0 0 !important;
        border:        1px solid rgba(255,255,255,.07) !important;
        border-bottom: none !important;
        padding:       .45rem 1.2rem !important;
        transition:    background .2s, color .2s !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        background: rgba(242,133,0,.12) !important;
        color:      rgba(255,255,255,.7) !important;
    }
    /* Aktif sekme — turuncu degrade + beyaz metin */
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #F28500 0%, #D46000 100%) !important;
        color:      #ffffff !important;
        border-color: transparent !important;
        box-shadow: 0 -2px 10px rgba(242,133,0,.35) !important;
    }
    [data-testid="stTabsContent"] { background: transparent !important; }

    /* ══════════════════════════════════════════════════
       4. INPUT ALANLARI — beyaz zemin, düzenli köşe
    ══════════════════════════════════════════════════ */
    [data-testid="stTextInput"] label p {
        color: rgba(180,210,230,.85) !important;
        font-size: .83rem !important;
        font-weight: 500 !important;
    }
    /* Tüm wrapper div'ler — beyaz arka plan, yuvarlak köşe */
    [data-testid="stTextInput"] > div,
    [data-testid="stTextInput"] > div > div,
    [data-testid="stTextInput"] > div > div > div {
        background:    #ffffff !important;
        border-radius: 9px !important;
        border:        none !important;
        overflow:      hidden !important;
    }
    /* Outer border — wrapper üzerinde */
    [data-testid="stTextInput"] > div {
        border: 1px solid rgba(19,78,94,0.5) !important;
        transition: border-color .2s, box-shadow .2s !important;
    }
    [data-testid="stTextInput"] > div:focus-within {
        border-color: rgba(242,133,0,.75) !important;
        box-shadow:   0 0 0 3px rgba(242,133,0,.18),
                      0 0 8px rgba(242,133,0,.12) !important;
    }
    /* Input — beyaz, koyu metin */
    [data-testid="stTextInput"] input {
        background:    #ffffff !important;
        border:        none !important;
        border-radius: 0 !important;
        color:         #0d2433 !important;
        font-size:     .92rem !important;
    }
    [data-testid="stTextInput"] input::placeholder {
        color: rgba(100,130,150,.5) !important;
    }
    /* Göz-ikonu butonu — beyaz zemin, siyah ikon */
    [data-testid="stTextInput"] button,
    [data-testid="stTextInput"] button:hover,
    [data-testid="stTextInput"] button:focus {
        background:    #ffffff !important;
        border:        none !important;
        box-shadow:    none !important;
        color:         #0d2433 !important;
    }
    [data-testid="stTextInput"] button svg,
    [data-testid="stTextInput"] button svg * {
        fill:   #0d2433 !important;
        stroke: #0d2433 !important;
        color:  #0d2433 !important;
    }

    /* Tooltip (?) ikonu — belirgin görünüm */
    [data-testid="stTooltipIcon"] svg,
    [data-testid="stTooltipIcon"] svg * {
        fill:   rgba(242,133,0,.85) !important;
        stroke: rgba(242,133,0,.85) !important;
    }
    [data-testid="stTooltipIcon"]:hover svg,
    [data-testid="stTooltipIcon"]:hover svg * {
        fill:   #F28500 !important;
        stroke: #F28500 !important;
    }

    /* ══════════════════════════════════════════════════
       5. FORM SUBMIT BUTONU — gümüş-gri/mavi degrade, siyah yazı
    ══════════════════════════════════════════════════ */
    [data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg,
            #8eb8cc 0%,
            #6a9db8 40%,
            #7aafc6 100%) !important;
        color:         #0a1e28 !important;
        border:        none !important;
        border-radius: 28px !important;
        font-weight:   800 !important;
        font-size:     .95rem !important;
        letter-spacing:.05em !important;
        box-shadow:    0 3px 14px rgba(0,0,0,.35),
                       0 1px 0   rgba(255,255,255,.2) inset !important;
        transition:    transform .15s, box-shadow .15s, filter .15s !important;
        padding:       .65rem !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover {
        filter:    brightness(1.08) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(0,0,0,.4) !important;
    }
    [data-testid="stFormSubmitButton"] > button:active {
        transform: translateY(0) !important;
        filter:    brightness(.96) !important;
    }

    /* ── Hata / uyarı kutuları ── */
    [data-testid="stAlert"] {
        background:   rgba(10,37,51,.55) !important;
        border:       1px solid rgba(242,133,0,.25) !important;
        border-radius: 10px !important;
        color: #dff0f8 !important;
    }

    /* ══════════════════════════════════════════════════
       6. FOOTER — yapışık kapsül
    ══════════════════════════════════════════════════ */
    .ro-login-footer {
        position:   fixed;
        bottom:     18px;
        left:       50%;
        transform:  translateX(-50%);
        display:    inline-flex;
        align-items: center;
        gap:        .6rem;
        background: rgba(10, 30, 42, 0.72);
        backdrop-filter: blur(8px);
        border:     1px solid rgba(255,255,255,.08);
        border-radius: 40px;
        padding:    .38rem 1.2rem;
        font-size:  .71rem;
        color:      rgba(255,255,255,.45);
        letter-spacing: .05em;
        white-space: nowrap;
        z-index:    9999;
        pointer-events: none;
    }
    .ro-login-footer span { pointer-events: all; }
    .ro-login-footer a {
        color: rgba(255,255,255,.45) !important;
        text-decoration: none !important;
        pointer-events: all;
        transition: color .2s;
    }
    .ro-login-footer a:hover { color: #F28500 !important; }
    .ro-sep { opacity: .3; }
    </style>
    """, unsafe_allow_html=True)

    # ── Orta kolon layout ────────────────────────────────────────────────────
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        st.markdown(
            """
            <div style="text-align:center; margin-bottom:1.8rem; padding-top:.4rem;">
                <div style="font-size:3rem; margin-bottom:.35rem;
                            filter:drop-shadow(0 0 18px rgba(242,133,0,.55));">🔄</div>
                <h1 style="color:#e8f4fa; font-size:2rem; font-weight:800;
                           margin:.15rem 0 .1rem; letter-spacing:-.01em;
                           text-shadow:0 2px 14px rgba(0,0,0,.5);">ReOrder</h1>
                <p style="color:rgba(180,210,230,.7); margin:.2rem 0 0; font-size:.86rem;
                          font-weight:400;">
                    Trendyol Retention & Müşteri Analiz Platformu
                </p>
                <p style="font-size:.82rem; font-style:italic; font-weight:700; margin:.5rem 0 0;
                          letter-spacing:.04em;
                          background: linear-gradient(90deg,#F28500,#ffb347);
                          -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                          background-clip:text;">
                    Seamless Experience, Return Customers.&nbsp;|&nbsp;Kusursuz Deneyim, Geri Dönen Müşteriler.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_giris, tab_kayit = st.tabs(["🔐 Giriş Yap", "✨ Hesap Oluştur"])

        with tab_giris:
            with st.form("login_form"):
                email = st.text_input("E-posta", placeholder="ornek@magaza.com")
                password = st.text_input("Şifre", type="password")
                submitted = st.form_submit_button("Giriş Yap", use_container_width=True)
            if submitted:
                res = login_user(email, password)
                if res["success"]:
                    st.session_state.user = res["user"]
                    st.rerun()
                else:
                    st.error(res["error"])

        with tab_kayit:
            with st.form("register_form"):
                store = st.text_input("Mağaza Adı", placeholder="Mağazanızın adı")
                email2 = st.text_input("E-posta", placeholder="ornek@magaza.com")
                pw1 = st.text_input("Şifre", type="password", help="En az 8 karakter, 1 rakam içermeli")
                pw2 = st.text_input("Şifre (Tekrar)", type="password")
                sub2 = st.form_submit_button("Hesap Oluştur", use_container_width=True)
            if sub2:
                if pw1 != pw2:
                    st.error("Şifreler eşleşmiyor.")
                else:
                    res = register_user(email2, pw1, store)
                    if res["success"]:
                        st.session_state.user = res["user"]
                        st.rerun()
                    else:
                        st.error(res["error"])

    # ── Footer kapsülü ───────────────────────────────────────────────────────
    st.markdown(
        '<div class="ro-login-footer">'
        '<span>ReOrder &copy; 2026</span>'
        '<span class="ro-sep">|</span>'
        '<a href="mailto:support@reorder.app">❓ Support</a>'
        '<span class="ro-sep">|</span>'
        '<a href="#">⭕ Privacy Policy</a>'
        '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
def show_sidebar() -> None:
    user = st.session_state.user
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding:.8rem .2rem 1.2rem; border-bottom:1px solid rgba(255,255,255,.1);">
                <div style="font-size:1.4rem; font-weight:700; color:#F27A1A;">🔄 ReOrder</div>
                <div style="font-size:.8rem; margin-top:.3rem; opacity:.7;">{user['store_name']}</div>
                <div style="font-size:.72rem; opacity:.5;">{user['email']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("&nbsp;")

        pages = [
            ("📊", "Genel Bakış", "dashboard"),
            ("📁", "Veri Yükle", "upload"),
            ("📈", "Analitik", "analytics"),
            ("👥", "Müşteri Segmentleri", "segments"),
            ("⚙️", "Ayarlar", "settings"),
        ]
        for icon, label, key in pages:
            if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True):
                _go(key)

        st.markdown("---")
        if st.button("🚪  Çıkış Yap", use_container_width=True, key="logout_btn"):
            st.session_state.user = None
            st.session_state.page = "dashboard"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Genel Bakış
# ─────────────────────────────────────────────────────────────────────────────
def show_dashboard() -> None:
    user = st.session_state.user
    _header("📊", "Genel Bakış", f"{user['store_name']} — Müşteri Metrikleri")

    m = get_summary_metrics(user["id"])

    if not m["has_data"]:
        st.markdown(
            """<div class="info-box">📂 <b>Henüz veri yüklenmedi.</b> Analitikleri görmek için
            <b>Veri Yükle</b> sayfasından Trendyol sipariş raporu yükleyin veya örnek veri oluşturun.</div>""",
            unsafe_allow_html=True,
        )
        if st.button("📁 Veri Yükle Sayfasına Git"):
            _go("upload")
        return

    # ── KPI Satırı 1 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi("Toplam Sipariş", f"{m['total_orders']:,}")
    with c2:
        _kpi("Benzersiz Müşteri", f"{m['unique_customers']:,}")
    with c3:
        _kpi("Toplam Gelir", _fmt_tl(m["total_revenue"]))
    with c4:
        _kpi("Ort. Sipariş Değeri", _fmt_tl(m["avg_order_value"]))

    st.markdown("&nbsp;")

    # ── KPI Satırı 2 ──
    c1, c2, c3, _ = st.columns(4)
    with c1:
        _kpi(
            "Tekrar Eden Müşteriler",
            f"%{m['repeat_rate']}",
            f"{m['repeat_customers']:,} müşteri geri döndü",
        )
    with c2:
        _kpi("Ortalama LTV", _fmt_tl(m["avg_ltv"]), "Müşteri başı ömür boyu değer")
    with c3:
        _kpi("En Yüksek LTV", _fmt_tl(m["top_customer_revenue"]), "Tek müşteri rekoru")

    st.markdown("&nbsp;")

    # ── Grafikler ──
    trend = get_monthly_trend(user["id"])
    nvr = get_new_vs_returning(user["id"])

    gcol1, gcol2 = st.columns(2)

    with gcol1:
        _section("Aylık Gelir Trendi")
        if not trend.empty:
            fig = px.area(
                trend,
                x="month_str",
                y="revenue",
                labels={"month_str": "Ay", "revenue": "Gelir (₺)"},
                color_discrete_sequence=["#F27A1A"],
                template="plotly_white",
            )
            fig.update_layout(
                height=280, margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="", yaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)

    with gcol2:
        _section("Yeni vs Geri Dönen Müşteri")
        if not nvr.empty:
            cols_needed = [c for c in ["yeni_musteri", "geri_donen"] if c in nvr.columns]
            if cols_needed:
                fig2 = go.Figure()
                colors = {"yeni_musteri": "#F27A1A", "geri_donen": "#3B82F6"}
                labels = {"yeni_musteri": "Yeni", "geri_donen": "Geri Dönen"}
                for col in cols_needed:
                    fig2.add_trace(
                        go.Bar(
                            name=labels[col],
                            x=nvr["month_str"],
                            y=nvr[col],
                            marker_color=colors[col],
                        )
                    )
                fig2.update_layout(
                    barmode="stack",
                    height=280,
                    margin=dict(l=0, r=0, t=10, b=0),
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1),
                    xaxis_title="", yaxis_title="",
                )
                st.plotly_chart(fig2, use_container_width=True)

    # ── Aylık sipariş tablosu ──
    _section("Aylık Özet Tablosu")
    if not trend.empty:
        display = trend[["month_str", "orders", "revenue", "unique_customers"]].copy()
        display.columns = ["Ay", "Sipariş", "Gelir (₺)", "Benzersiz Müşteri"]
        display["Gelir (₺)"] = display["Gelir (₺)"].apply(_fmt_tl)
        st.dataframe(display.sort_values("Ay", ascending=False), use_container_width=True, hide_index=True)

    # ── PDF Rapor İndir ──
    st.markdown("&nbsp;")
    _section("📄 PDF Rapor")
    st.markdown(
        """<div class="info-box">Tüm metrikleri, cohort matrisini ve müşteri segmentlerini
        tek sayfalık PDF raporu olarak indirin. Mağaza raporlaması veya arşivleme için idealdir.</div>""",
        unsafe_allow_html=True,
    )
    if st.button("📄 PDF Raporu Hazırla", key="pdf_generate_btn"):
        with st.spinner("PDF hazırlanıyor…"):
            try:
                pdf_bytes = generate_report(user["id"], user["store_name"])
                fname = f"reorder_rapor_{user['store_name'].replace(' ', '_')}_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="⬇️ PDF'i İndir",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    key="pdf_download_btn",
                )
                st.success("✅ PDF hazır! Yukarıdaki butona tıklayarak indirebilirsiniz.")
            except Exception as e:
                st.error(f"PDF oluşturulurken hata: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Veri Yükle
# ─────────────────────────────────────────────────────────────────────────────
def show_upload() -> None:
    user = st.session_state.user
    _header("📁", "Veri Yükle", "Trendyol sipariş raporunuzu içe aktarın")

    tab_file, tab_api, tab_sample, tab_manage = st.tabs(
        ["📂 Dosya Yükle", "🔌 Trendyol API", "🎲 Örnek Veri", "🗑️ Veri Yönetimi"]
    )

    # ── Dosya Yükle ──────────────────────────────────────────────────────────
    with tab_file:
        st.markdown(
            """<div class="info-box">
            <b>Nasıl yapılır?</b><br>
            Trendyol Satıcı Paneli → <b>Siparişlerim</b> → <b>Excel İndir</b> butonuyla indirdiğiniz
            <code>.xlsx</code> veya <code>.csv</code> dosyasını buraya yükleyin.
            Sistem sütunları otomatik tanır.
            </div>""",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Trendyol Sipariş Raporu (.xlsx, .csv)",
            type=["xlsx", "xls", "csv"],
            key="file_uploader",
        )

        if uploaded:
            with st.spinner("Dosya analiz ediliyor…"):
                result = parse_trendyol_file(uploaded)

            if not result["success"]:
                for err in result["errors"]:
                    st.error(err)
                st.markdown(
                    """<div class="warn-box">
                    <b>İpucu:</b> Trendyol'dan indirdiğiniz orijinal Excel dosyasını (formatı değiştirmeden) yükleyin.
                    Sütun adları Türkçe veya İngilizce olabilir.
                    </div>""",
                    unsafe_allow_html=True,
                )
                return

            for warn in result["warnings"]:
                st.warning(warn)

            df = result["data"]
            col_map = result["col_map"]

            _section("Tespit Edilen Sütunlar")
            field_labels = {
                "order_number": "Sipariş No",
                "customer_identifier": "Müşteri",
                "order_date": "Tarih",
                "total_amount": "Tutar",
                "product_name": "Ürün",
                "quantity": "Adet",
                "status": "Durum",
            }
            col_info = {field_labels.get(k, k): v for k, v in col_map.items()}
            st.json(col_info)

            _section(f"Ön İzleme ({len(df):,} satır)")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

            if st.button("✅ Veritabanına Aktar", type="primary"):
                with st.spinner("Aktarılıyor…"):
                    imp = import_to_db(df, user["id"])
                st.markdown(
                    f"""<div class="success-box">
                    ✅ <b>{imp['inserted']:,} yeni sipariş</b> aktarıldı.
                    {f"({imp['skipped']:,} tekrar atlandı.)" if imp['skipped'] else ""}
                    </div>""",
                    unsafe_allow_html=True,
                )
                if st.button("📊 Analizlere Git"):
                    _go("dashboard")

    # ── Trendyol API ─────────────────────────────────────────────────────────
    with tab_api:
        creds = load_credentials(user["id"])

        if not creds:
            st.markdown(
                """<div class="warn-box">
                🔌 <b>API bağlantısı kurulmamış.</b>
                Aşağıya Trendyol Satıcı Paneli'nden aldığınız bilgileri girerek bağlantıyı kurun.
                Sonraki senkronizasyonlarda bu bilgiler otomatik kullanılır.
                <br><br>
                <b>Nasıl alınır?</b> Trendyol Satıcı Paneli →
                <b>Entegrasyonlar</b> → <b>API Entegrasyonları</b> → API Bilgileri
                </div>""",
                unsafe_allow_html=True,
            )

        # Credential formu
        with st.expander("🔑 API Kimlik Bilgileri" + (" (Kayıtlı ✅)" if creds else ""), expanded=not bool(creds)):
            with st.form("api_creds_form"):
                seller_id  = st.text_input("Satıcı ID",   value=creds["seller_id"]  if creds else "", placeholder="Örn: 12345")
                api_key    = st.text_input("API Key",      value=creds["api_key"]    if creds else "", placeholder="Trendyol API Key")
                api_secret = st.text_input("API Secret",   value=creds["api_secret"] if creds else "", type="password", placeholder="Trendyol API Secret")

                col_save, col_test = st.columns(2)
                with col_save:
                    save_btn = st.form_submit_button("💾 Kaydet", use_container_width=True)
                with col_test:
                    test_btn = st.form_submit_button("🔗 Bağlantıyı Test Et", use_container_width=True)

            if save_btn:
                if not (seller_id and api_key and api_secret):
                    st.error("Tüm alanları doldurun.")
                else:
                    save_credentials(user["id"], seller_id, api_key, api_secret)
                    st.success("✅ API bilgileri kaydedildi!")
                    st.rerun()

            if test_btn:
                if not (seller_id and api_key and api_secret):
                    st.error("Önce bilgileri girin.")
                else:
                    with st.spinner("Bağlantı test ediliyor…"):
                        try:
                            client = TrendyolClient(seller_id, api_key, api_secret)
                            ok = client.test_connection()
                        except Exception as e:
                            ok = False
                    if ok:
                        st.success("✅ Bağlantı başarılı! API bilgileri doğru.")
                    else:
                        st.error("❌ Bağlantı kurulamadı. Bilgilerinizi kontrol edin.")

        # Senkronizasyon paneli (sadece credentials varsa göster)
        if creds:
            st.markdown("---")
            _section("📥 Sipariş Senkronizasyonu")

            if creds["last_sync_at"]:
                st.markdown(
                    f"""<div class="success-box">
                    ⏱️ Son senkronizasyon: <b>{creds['last_sync_at']}</b>
                    — {creds['last_sync_count']:,} sipariş eklendi
                    </div>""",
                    unsafe_allow_html=True,
                )

            st.markdown("Trendyol'dan çekilecek tarih aralığını seçin:")

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("Son 7 Gün",  key="sync_7",  use_container_width=True):
                    st.session_state["sync_preset"] = 7
            with col2:
                if st.button("Son 30 Gün", key="sync_30", use_container_width=True):
                    st.session_state["sync_preset"] = 30
            with col3:
                if st.button("Son 90 Gün", key="sync_90", use_container_width=True):
                    st.session_state["sync_preset"] = 90

            import datetime as _dt
            preset_days = st.session_state.get("sync_preset", 30)
            default_start = _dt.date.today() - _dt.timedelta(days=preset_days)
            default_end   = _dt.date.today()

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                sync_start = st.date_input("Başlangıç", value=default_start, key="sync_start")
            with col_d2:
                sync_end   = st.date_input("Bitiş",     value=default_end,   key="sync_end")

            if st.button("🔄 Siparişleri Senkronize Et", type="primary", use_container_width=True):
                if sync_start > sync_end:
                    st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
                else:
                    with st.spinner(f"Trendyol'dan siparişler çekiliyor ({sync_start} → {sync_end})…"):
                        result = sync_orders(
                            user["id"],
                            sync_start.strftime("%Y-%m-%d"),
                            sync_end.strftime("%Y-%m-%d"),
                        )

                    if result["success"]:
                        if result["inserted"] == 0 and result["skipped"] == 0:
                            st.info("Bu tarih aralığında yeni sipariş bulunamadı.")
                        else:
                            st.markdown(
                                f"""<div class="success-box">
                                ✅ Senkronizasyon tamamlandı!<br>
                                <b>{result['inserted']:,} yeni sipariş</b> eklendi.
                                {f"({result['skipped']:,} tekrar atlandı.)" if result['skipped'] else ""}
                                </div>""",
                                unsafe_allow_html=True,
                            )
                            if st.button("📊 Dashboard'a Git", key="api_goto_dash"):
                                _go("dashboard")
                    else:
                        st.error(f"❌ Hata: {result['error']}")

    # ── Örnek Veri ───────────────────────────────────────────────────────────
    with tab_sample:
        st.markdown(
            """<div class="info-box">
            Gerçek veriniz yokken ReOrder'ı test etmek için 120 müşteri ve ~200 siparişten
            oluşan sentetik veri yükleyin.
            </div>""",
            unsafe_allow_html=True,
        )
        n_cust = st.slider("Müşteri sayısı", 30, 300, 120, step=10)
        if st.button("🎲 Örnek Veri Oluştur & Yükle", type="primary"):
            with st.spinner("Örnek veri oluşturuluyor…"):
                sample_df = generate_sample_orders(n_customers=n_cust)
                imp = import_to_db(sample_df, user["id"], batch="sample_data")
            st.markdown(
                f"""<div class="success-box">
                🎉 <b>{imp['inserted']:,} örnek sipariş</b> yüklendi!
                {n_cust} müşteri için 12 aylık veri hazır.
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("📊 Dashboard'a Git"):
                _go("dashboard")

    # ── Veri Yönetimi ────────────────────────────────────────────────────────
    with tab_manage:
        from src.database import delete_all_orders
        from src.analytics import get_summary_metrics as _sm

        m = _sm(user["id"])
        if m["has_data"]:
            st.markdown(
                f"""<div class="warn-box">
                ⚠️ Şu anda <b>{m['total_orders']:,} sipariş</b> kayıtlı.
                Tüm verileri silmek geri alınamaz!
                </div>""",
                unsafe_allow_html=True,
            )
            confirm = st.checkbox("Evet, tüm sipariş verilerimi silmek istiyorum")
            if confirm:
                if st.button("🗑️ Tüm Verileri Sil", type="primary"):
                    cnt = delete_all_orders(user["id"])
                    st.success(f"{cnt:,} sipariş silindi.")
                    st.rerun()
        else:
            st.info("Henüz veri yüklenmemiş.")


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Analitik
# ─────────────────────────────────────────────────────────────────────────────
def show_analytics() -> None:
    user = st.session_state.user
    _header("📈", "Analitik", "Cohort Retention, LTV ve Müşteri Davranışı")

    m = get_summary_metrics(user["id"])
    if not m["has_data"]:
        st.info("Veri bulunamadı. Lütfen önce sipariş yükleyin.")
        return

    tab_cohort, tab_ltv, tab_retention = st.tabs(
        ["🔢 Cohort Analizi", "💰 LTV Analizi", "📉 Retention Trendi"]
    )

    # ── Cohort ───────────────────────────────────────────────────────────────
    with tab_cohort:
        _section("Aylık Cohort Retention Matrisi")
        st.markdown(
            """<div class="info-box" style="font-size:.82rem;">
            Her satır bir <b>cohort</b> (o ay ilk kez alışveriş yapan müşteriler).
            Sütunlar ilk alışverişten sonraki ayları gösterir.
            %100 = tüm cohort o ayda aktifti.
            </div>""",
            unsafe_allow_html=True,
        )
        ret_df, cohort_sizes = get_cohort_retention(user["id"])
        if ret_df.empty:
            st.info("Cohort analizi için en az 2 farklı müşteriye ihtiyaç var.")
        else:
            # Maks 12 ay göster
            show_cols = [c for c in ret_df.columns if c <= 11]
            display = ret_df[show_cols].copy()

            # Heatmap
            z = display.values.tolist()
            x_labels = [f"Ay {int(c)}" for c in show_cols]
            y_labels = [str(p) for p in display.index]
            text_labels = [
                [f"{v:.0f}%" if v > 0 else "" for v in row]
                for row in display.values
            ]

            fig = go.Figure(
                go.Heatmap(
                    z=z,
                    x=x_labels,
                    y=y_labels,
                    text=text_labels,
                    texttemplate="%{text}",
                    textfont={"size": 11},
                    colorscale="RdYlGn",
                    zmin=0,
                    zmax=100,
                    colorbar=dict(title="Retention %"),
                )
            )
            fig.update_layout(
                height=max(300, len(y_labels) * 38 + 80),
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis_title="İlk Alışverişten Sonraki Ay",
                yaxis_title="Cohort Ayı",
                template="plotly_white",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True)

            _section("Cohort Boyutları")
            sizes_df = pd.DataFrame(
                {"Cohort Ayı": cohort_sizes.index.astype(str), "Müşteri Sayısı": cohort_sizes.values}
            )
            fig2 = px.bar(
                sizes_df,
                x="Cohort Ayı",
                y="Müşteri Sayısı",
                color_discrete_sequence=["#F27A1A"],
                template="plotly_white",
            )
            fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    # ── LTV ──────────────────────────────────────────────────────────────────
    with tab_ltv:
        ltv_df = get_ltv_distribution(user["id"])
        top10 = get_top_customers(user["id"])

        if ltv_df.empty:
            st.info("LTV verisi yok.")
        else:
            c1, c2 = st.columns(2)

            with c1:
                _section("LTV Dağılımı (Histogram)")
                fig = px.histogram(
                    ltv_df,
                    x="ltv",
                    nbins=30,
                    labels={"ltv": "Müşteri LTV (₺)"},
                    color_discrete_sequence=["#F27A1A"],
                    template="plotly_white",
                )
                fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                                  yaxis_title="Müşteri Sayısı")
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                _section("En İyi 10 Müşteri")
                if not top10.empty:
                    fig2 = px.bar(
                        top10.head(10),
                        x="ltv",
                        y="musteri",
                        orientation="h",
                        labels={"ltv": "LTV (₺)", "musteri": ""},
                        color_discrete_sequence=["#3B82F6"],
                        template="plotly_white",
                    )
                    fig2.update_layout(
                        height=280, margin=dict(l=0, r=0, t=10, b=0),
                        yaxis=dict(autorange="reversed"),
                    )
                    st.plotly_chart(fig2, use_container_width=True)

            # Pareto analizi
            _section("Pareto Analizi (80/20 Kuralı)")
            ltv_sorted = ltv_df.sort_values("ltv", ascending=False).reset_index(drop=True)
            total_rev = ltv_sorted["ltv"].sum()
            ltv_sorted["cumulative_pct"] = ltv_sorted["ltv"].cumsum() / total_rev * 100
            ltv_sorted["customer_pct"] = (ltv_sorted.index + 1) / len(ltv_sorted) * 100

            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=ltv_sorted["customer_pct"],
                y=ltv_sorted["cumulative_pct"],
                fill="tozeroy",
                line=dict(color="#F27A1A", width=2),
                name="Kümülatif Gelir",
            ))
            fig3.add_hline(y=80, line_dash="dash", line_color="#6B7280", annotation_text="80%")
            fig3.update_layout(
                height=260,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Müşteri % (LTV'ye göre sıralı)",
                yaxis_title="Kümülatif Gelir %",
                template="plotly_white",
            )
            st.plotly_chart(fig3, use_container_width=True)

    # ── Retention Trendi ─────────────────────────────────────────────────────
    with tab_retention:
        _section("Aylık Retention Oranı Trendi")
        nvr = get_new_vs_returning(user["id"])
        trend = get_monthly_trend(user["id"])

        if nvr.empty or trend.empty:
            st.info("Yeterli veri yok.")
        else:
            # Retention = geri_donen / (yeni + geri_donen)
            merged = nvr.merge(trend[["month_str", "orders"]], on="month_str", how="left")
            if "yeni_musteri" in merged.columns and "geri_donen" in merged.columns:
                merged["total_customers"] = merged.get("yeni_musteri", 0) + merged.get("geri_donen", 0)
                merged["retention_rate"] = (
                    merged.get("geri_donen", 0) / merged["total_customers"].replace(0, np.nan) * 100
                ).round(1)

                fig = px.line(
                    merged,
                    x="month_str",
                    y="retention_rate",
                    markers=True,
                    labels={"month_str": "Ay", "retention_rate": "Retention Oranı (%)"},
                    color_discrete_sequence=["#10B981"],
                    template="plotly_white",
                )
                fig.update_traces(line=dict(width=2.5))
                fig.update_layout(
                    height=300, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(range=[0, 100], ticksuffix="%"),
                )
                st.plotly_chart(fig, use_container_width=True)

                _section("Aylık Sipariş Hacmi")
                fig2 = px.bar(
                    trend,
                    x="month_str",
                    y="orders",
                    labels={"month_str": "Ay", "orders": "Sipariş Sayısı"},
                    color_discrete_sequence=["#F27A1A"],
                    template="plotly_white",
                )
                fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Müşteri Segmentleri
# ─────────────────────────────────────────────────────────────────────────────
def show_segments() -> None:
    user = st.session_state.user
    _header("👥", "Müşteri Segmentleri", "RFM tabanlı otomatik segmentasyon")

    m = get_summary_metrics(user["id"])
    if not m["has_data"]:
        st.info("Veri bulunamadı.")
        return

    segments_df = get_customer_segments(user["id"])
    if segments_df.empty:
        st.info("Yeterli veri yok.")
        return

    # Segment özeti
    seg_summary = (
        segments_df.groupby("segment")
        .agg(musteri_sayisi=("customer_identifier", "count"), toplam_gelir=("total_revenue", "sum"))
        .reset_index()
        .sort_values("musteri_sayisi", ascending=False)
    )

    c1, c2 = st.columns(2)

    with c1:
        _section("Segment Dağılımı")
        colors = {
            "Sadık Müşteri": "#10B981",
            "Gelişen Müşteri": "#3B82F6",
            "Yeni Müşteri": "#F59E0B",
            "Risk Altında": "#EF4444",
            "Tek Alışveriş": "#9CA3AF",
            "Kaybolma Riski": "#6B7280",
        }
        fig = px.pie(
            seg_summary,
            names="segment",
            values="musteri_sayisi",
            color="segment",
            color_discrete_map=colors,
            hole=0.45,
            template="plotly_white",
        )
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        _section("Gelir Katkısı")
        fig2 = px.bar(
            seg_summary,
            x="segment",
            y="toplam_gelir",
            color="segment",
            color_discrete_map=colors,
            labels={"segment": "", "toplam_gelir": "Gelir (₺)"},
            template="plotly_white",
        )
        fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Tablo
    _section("Segment Detay Tablosu")
    table = seg_summary.copy()
    table["toplam_gelir"] = table["toplam_gelir"].apply(_fmt_tl)
    table.columns = ["Segment", "Müşteri Sayısı", "Toplam Gelir"]
    st.dataframe(table, use_container_width=True, hide_index=True)

    _section("Müşteri Listesi (İlk 100)")
    show_cols = ["customer_identifier", "segment", "total_orders", "total_revenue",
                 "avg_order_value", "days_since_last"]
    col_rename = {
        "customer_identifier": "Müşteri",
        "segment": "Segment",
        "total_orders": "Sipariş",
        "total_revenue": "Toplam Harcama",
        "avg_order_value": "Ort. Sipariş",
        "days_since_last": "Son Alışveriş (Gün)",
    }
    display = segments_df[show_cols].rename(columns=col_rename).head(100)
    display["Toplam Harcama"] = display["Toplam Harcama"].apply(_fmt_tl)
    display["Ort. Sipariş"] = display["Ort. Sipariş"].apply(_fmt_tl)
    st.dataframe(display, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Ayarlar
# ─────────────────────────────────────────────────────────────────────────────
def show_settings() -> None:
    user = st.session_state.user
    _header("⚙️", "Ayarlar", "Hesap ve mağaza bilgilerinizi yönetin")

    tab_account, tab_api = st.tabs(["👤 Hesap Bilgileri", "🔌 Trendyol API (Pro)"])

    with tab_account:
        st.subheader("Mağaza Adı")
        with st.form("store_name_form"):
            new_store = st.text_input("Mağaza Adı", value=user["store_name"])
            if st.form_submit_button("Güncelle"):
                res = update_store_name(user["id"], new_store)
                if res["success"]:
                    st.session_state.user["store_name"] = new_store
                    st.success("Mağaza adı güncellendi.")
                    st.rerun()
                else:
                    st.error(res["error"])

        st.subheader("Şifre Değiştir")
        with st.form("change_pw_form"):
            old_pw = st.text_input("Mevcut Şifre", type="password")
            new_pw = st.text_input("Yeni Şifre", type="password")
            new_pw2 = st.text_input("Yeni Şifre (Tekrar)", type="password")
            if st.form_submit_button("Şifreyi Değiştir"):
                if new_pw != new_pw2:
                    st.error("Yeni şifreler eşleşmiyor.")
                else:
                    res = change_password(user["id"], old_pw, new_pw)
                    if res["success"]:
                        st.success("Şifre başarıyla değiştirildi.")
                    else:
                        st.error(res["error"])

    with tab_api:
        creds_s = load_credentials(user["id"])
        st.markdown(
            """<div class="info-box">
            🔌 <b>Trendyol API Entegrasyonu</b><br>
            Buraya kaydettiğiniz bilgiler <b>Veri Yükle → Trendyol API</b> sekmesinde
            otomatik olarak kullanılır. Siparişlerinizi manuel dosya yüklemeden doğrudan çekebilirsiniz.
            <br><br>
            <b>Nasıl alınır?</b> Trendyol Satıcı Paneli → <b>Entegrasyonlar → API Entegrasyonları</b>
            </div>""",
            unsafe_allow_html=True,
        )
        if creds_s:
            st.markdown(
                f"""<div class="success-box">
                ✅ API bağlantısı kayıtlı — Satıcı ID: <b>{creds_s['seller_id']}</b><br>
                Son senkronizasyon: {creds_s['last_sync_at'] or 'Henüz yapılmadı'}
                </div>""",
                unsafe_allow_html=True,
            )
        with st.form("api_settings_form"):
            s_seller = st.text_input("Satıcı ID",  value=creds_s["seller_id"]  if creds_s else "")
            s_key    = st.text_input("API Key",    value=creds_s["api_key"]    if creds_s else "")
            s_secret = st.text_input("API Secret", value=creds_s["api_secret"] if creds_s else "", type="password")
            col1, col2 = st.columns(2)
            with col1:
                save_s = st.form_submit_button("💾 Kaydet", use_container_width=True)
            with col2:
                test_s = st.form_submit_button("🔗 Test Et", use_container_width=True)

        if save_s:
            if not (s_seller and s_key and s_secret):
                st.error("Tüm alanları doldurun.")
            else:
                save_credentials(user["id"], s_seller, s_key, s_secret)
                st.success("✅ API bilgileri kaydedildi!")
                st.rerun()
        if test_s:
            if not (s_seller and s_key and s_secret):
                st.error("Önce bilgileri girin.")
            else:
                with st.spinner("Test ediliyor…"):
                    try:
                        ok = TrendyolClient(s_seller, s_key, s_secret).test_connection()
                    except Exception:
                        ok = False
                if ok:
                    st.success("✅ Bağlantı başarılı!")
                else:
                    st.error("❌ Bağlantı başarısız. Bilgilerinizi kontrol edin.")


# ─────────────────────────────────────────────────────────────────────────────
# Yönlendirici
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    if st.session_state.user is None:
        show_auth()
        return

    show_sidebar()

    page = st.session_state.page
    if page == "dashboard":
        show_dashboard()
    elif page == "upload":
        show_upload()
    elif page == "analytics":
        show_analytics()
    elif page == "segments":
        show_segments()
    elif page == "settings":
        show_settings()
    else:
        show_dashboard()


main()
