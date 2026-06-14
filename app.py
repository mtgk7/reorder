"""
app.py — ReOrder Streamlit Web Arayüzü (Ana Giriş Noktası)
Çalıştırmak için: streamlit run app.py
Güncelleme: 2026-06-07
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
from datetime import datetime

from src.database import (
    init_db as _init_db, get_stores, create_store, rename_store, delete_store,
    save_goals, load_goals, link_null_orders, save_user_plan,
    create_reset_token, verify_reset_token, use_reset_token,
    get_or_create_referral_code, use_referral_code, get_referral_stats,
    get_weekly_report_settings, save_weekly_report_settings, mark_weekly_report_sent,
)
from src.auth import (
    login_user, register_user, update_store_name, change_password,
    create_session_token, verify_session_token, delete_session_token,
    send_reset_email, reset_password_with_token,
)
from src.parser import parse_trendyol_file, import_to_db, generate_sample_orders
# generate_report imported lazily inside show_analytics() to avoid loading fpdf2 at startup
from src.trendyol_api import (
    save_credentials, load_credentials, sync_orders,
    TrendyolClient, TrendyolAPIError,
)
from src.email_service import (
    save_smtp_settings, load_smtp_settings,
    send_test_email, send_campaign_report, send_weekly_summary,
    save_campaign_log, load_campaign_history,
    build_template, SEGMENT_TEMPLATES, SMTPConfig,
)
from src.analytics import (
    get_summary_metrics,
    get_cohort_retention,
    get_monthly_trend,
    get_new_vs_returning,
    get_customer_segments,
    get_ltv_distribution,
    get_top_customers,
    get_order_status_kpis,
    get_top_products,
    get_daily_revenue,
    get_customer_detail,
    get_current_month_metrics,
    get_product_analysis,
    # Yeni özellikler
    get_revenue_forecast,
    get_cross_sell_matrix,
    get_period_comparison,
    get_anomalies,
    get_segment_recommendations,
)
from src.ui_helpers import (
    _PLAN_LIMITS, _PLAN_BADGE_COLOR, _PLAN_UPGRADE, _PLAN_PRICES, _PLAN_FEATURES,
    _ONBOARDING_BG, _plan_limits, _plan_gate, _fmt_tl, _kpi, _header, _section, _go,
)

# ─────────────────────────────────────────────────────────────────────────────
# Başlatma — cache_resource ile yalnızca bir kez çalışır (rerun'larda atlanır)
# _SCHEMA_VER değiştiğinde cache kırılır ve init_db() yeniden çalışır.
# Yeni tablo/sütun eklendiğinde bu sabiti artır!
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA_VER = "v9"  # referrals + weekly_report + yeni özellikler


@st.cache_resource
def _init_db_once(_ver: str = _SCHEMA_VER):
    _init_db()


_init_db_once(_SCHEMA_VER)


from PIL import Image as _PIL_Image
from pathlib import Path as _Path
_favicon = _PIL_Image.open(_Path(__file__).parent / "assets" / "favicon.png")
st.set_page_config(
    page_title="ReOrder — Trendyol Retention",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="auto",   # mobilde kapalı, masaüstünde açık
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
        background: linear-gradient(135deg, #F27A1A 0%, #C95A10 100%);
        border-radius: 14px;
        padding: 1.1rem 1.6rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 0.9rem;
        box-shadow: 0 4px 18px rgba(242,122,26,.35);
        position: relative;
        overflow: hidden;
    }
    .app-header::after {
        content: "";
        position: absolute;
        right: -30px; top: -30px;
        width: 120px; height: 120px;
        border-radius: 50%;
        background: rgba(255,255,255,.06);
    }
    .app-header h1 { color: white !important; margin: 0; font-size: 1.5rem; font-weight: 800; }
    .app-header p  { color: rgba(255,255,255,.82) !important; margin: 0; font-size: .86rem; }

    /* ── KPI Kartları ── */
    .kpi-card {
        background: white;
        border-radius: 14px;
        padding: 1.15rem 1.3rem;
        border-left: 4px solid #F27A1A;
        box-shadow: 0 2px 10px rgba(0,0,0,.07);
        height: 100%;
        transition: transform .2s ease, box-shadow .2s ease;
        position: relative;
        overflow: hidden;
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 24px rgba(242,122,26,.18);
    }
    .kpi-card::after {
        content: "";
        position: absolute;
        bottom: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, #F27A1A, rgba(242,122,26,0));
    }
    .kpi-label { font-size: .72rem; font-weight: 700; color: #6B7280;
                 text-transform: uppercase; letter-spacing: .05em; margin-bottom: .3rem;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi-value { font-size: clamp(1.2rem, 2.2vw, 1.8rem); font-weight: 800; color: #1A1A2E;
                 line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi-sub   { font-size: .75rem; color: #9CA3AF; margin-top: .2rem; }

    /* ── Bölüm başlığı ── */
    .section-title {
        font-size: .92rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 1.5rem 0 .7rem 0;
        padding: .3rem .7rem .3rem .65rem;
        border-left: 3px solid #F27A1A;
        background: linear-gradient(90deg, rgba(242,122,26,.07), transparent);
        border-radius: 0 6px 6px 0;
        display: block;
        letter-spacing: .01em;
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

    /* ── Sidebar selectbox (mağaza seçici) ── */
    [data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
        background-color: rgba(255,255,255,0.1) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 8px !important;
        color: #E2E8F0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div > div,
    [data-testid="stSidebar"] [data-testid="stSelectbox"] span {
        color: #E2E8F0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] svg {
        fill: #E2E8F0 !important;
    }

    /* ── Sidebar expander (Mağaza Ekle / Yönet) ── */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background-color: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        border-radius: 10px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary * {
        color: #E2E8F0 !important;
        background: transparent !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        fill: #E2E8F0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] > div {
        background-color: transparent !important;
    }
    /* Expander içi tüm label ve yazılar */
    [data-testid="stSidebar"] [data-testid="stExpander"] label,
    [data-testid="stSidebar"] [data-testid="stExpander"] p,
    [data-testid="stSidebar"] [data-testid="stExpander"] span:not([class*="indicator"]) {
        color: #E2E8F0 !important;
    }
    /* "Press Enter to apply" hint yazısı */
    [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="InputInstructions"],
    [data-testid="stSidebar"] [data-testid="stExpander"] small {
        color: rgba(226,232,240,0.4) !important;
    }

    /* ── Sidebar text input — tüm katmanları hedefle ── */
    [data-testid="stSidebar"] [data-testid="stTextInput"],
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div,
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div > div,
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div > div > div {
        background-color: transparent !important;
        border-color: transparent !important;
    }
    /* Dış wrapper: görünür arka plan ve border */
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div {
        background-color: rgba(255,255,255,0.1) !important;
        border: 1px solid rgba(255,255,255,0.25) !important;
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div:focus-within {
        border-color: rgba(242,122,26,0.8) !important;
        box-shadow: 0 0 0 2px rgba(242,122,26,0.2) !important;
    }
    /* Input elementi */
    [data-testid="stSidebar"] [data-testid="stTextInput"] input {
        background: transparent !important;
        background-color: transparent !important;
        color: #E2E8F0 !important;
        caret-color: #F27A1A !important;
        -webkit-text-fill-color: #E2E8F0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder {
        color: rgba(226,232,240,0.4) !important;
        -webkit-text-fill-color: rgba(226,232,240,0.4) !important;
    }
    /* Sidebar caption ve yardım metinleri */
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] [data-testid="stCaption"] {
        color: rgba(226,232,240,0.5) !important;
    }

    /* ── Sidebar nav düğmeleri ── */
    [data-testid="stSidebar"] .stButton > button {
        background:    rgba(255,255,255,.08) !important;
        border:        1px solid rgba(255,255,255,.12) !important;
        color:         #E2E8F0 !important;
        width:         100%;
        text-align:    left;
        margin-bottom: .25rem;
        border-radius: 8px  !important;
        min-height:    44px !important;
    }
    [data-testid="stSidebar"] .stButton > button p,
    [data-testid="stSidebar"] [data-testid^="stBaseButton"] p {
        font-size: 0.78rem !important;
        line-height: 1.2   !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(242,122,26,.3) !important;
        color:      #ffffff !important;
    }

    /* ══════════════════════════════════════════════════════════════════
       SIDEBAR HAMBURGER BUTONU — KESİN ÇÖZÜM (tüm Streamlit sürümleri)

       Gerçek DOM analizi sonucu (2026-05):
         • Bu sürümde "stExpandSidebarButton" (header içi BUTTON)
         • Eski/gelecek sürümlerde "stSidebarCollapsedControl" (bağımsız div)
         • Sidebar içi kapama butonu: stSidebarCollapseButton

       Sorun: header {visibility:hidden} tüm header içeriğini gizliyor,
              stExpandSidebarButton da header içinde olduğu için görünmüyor.
       Çözüm: visibility:visible !important + position:fixed ile görünür yap.
    ══════════════════════════════════════════════════════════════════ */

    /* ── 1. stExpandSidebarButton (mevcut Streamlit versiyonu) ─────── */
    [data-testid="stExpandSidebarButton"] {
        visibility:      visible !important;   /* header:hidden'ı ezer */
        position:        fixed   !important;
        left:            12px    !important;
        top:             12px    !important;
        z-index:         9999    !important;
        width:           40px    !important;
        height:          40px    !important;
        display:         flex    !important;
        align-items:     center  !important;
        justify-content: center  !important;
        background:      rgba(40, 60, 75, 0.85) !important;
        border:          1px solid rgba(242, 133, 0, 0.5) !important;
        border-radius:   8px    !important;
        box-shadow:      0 0 10px rgba(242,133,0,.30),
                         0 0 22px rgba(242,133,0,.15),
                         0 4px 14px rgba(0,0,0,.45) !important;
        backdrop-filter: blur(8px) !important;
        transition:      box-shadow .3s ease-in-out, transform .15s ease,
                         border-color .2s ease !important;
        cursor:          pointer !important;
        padding:         2px    !important;
    }
    [data-testid="stExpandSidebarButton"]:hover {
        box-shadow:   0 0 15px rgba(242,133,0,.60),
                      0 0 34px rgba(242,133,0,.28),
                      0 4px 20px rgba(0,0,0,.55) !important;
        border-color: rgba(242,133,0,.85) !important;
        transform:    scale(1.07) !important;
    }
    [data-testid="stExpandSidebarButton"]:active {
        transform: scale(.96) !important;
    }
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="stExpandSidebarButton"] svg *,
    [data-testid="stExpandSidebarButton"] svg path {
        visibility: visible !important;
        fill:       #f28500  !important;
        stroke:     #f28500  !important;
        color:      #f28500  !important;
    }
    /* Material icon yazı da varsa (keyboard_double_arrow_right) */
    [data-testid="stExpandSidebarButton"] span {
        visibility: visible !important;
        color:      #f28500  !important;
    }

    /* ── 2. stSidebarCollapsedControl (eski/gelecek sürümler fallback) */
    div[data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarCollapsedControl"] {
        position:         fixed !important;
        left:             12px  !important;
        top:              12px  !important;
        z-index:          9999  !important;
        background-color: rgba(40, 60, 75, 0.85) !important;
        border:           1px solid rgba(242,133,0,.5) !important;
        border-radius:    8px  !important;
        box-shadow:       0 0 10px rgba(242,133,0,.30) !important;
        padding:          2px  !important;
        transition:       all .3s ease-in-out !important;
    }
    div[data-testid="stSidebarCollapsedControl"]:hover,
    [data-testid="stSidebarCollapsedControl"]:hover {
        box-shadow: 0 0 15px rgba(242,133,0,.60) !important;
    }
    div[data-testid="stSidebarCollapsedControl"] button,
    [data-testid="stSidebarCollapsedControl"] button {
        background: transparent !important;
        border:     none        !important;
        color:      #f28500     !important;
    }
    div[data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="stSidebarCollapsedControl"] svg path {
        fill:   #f28500 !important;
        stroke: #f28500 !important;
    }

    /* ── 3. Sidebar içi kapama butonu (stSidebarCollapseButton) ─────── */
    [data-testid="stSidebarCollapseButton"] button,
    section[data-testid="stSidebar"] > div:first-child button:first-child {
        background:      rgba(40,60,75,.85) !important;
        border:          1px solid rgba(242,133,0,.5) !important;
        border-radius:   8px  !important;
        min-width:       36px !important;
        min-height:      36px !important;
        box-shadow:      0 0 8px rgba(242,133,0,.25),
                         0 4px 12px rgba(0,0,0,.4) !important;
        transition:      box-shadow .25s, transform .15s !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover,
    section[data-testid="stSidebar"] > div:first-child button:first-child:hover {
        box-shadow:  0 0 14px rgba(242,133,0,.55),
                     0 4px 18px rgba(0,0,0,.5) !important;
        transform:   scale(1.07) !important;
    }
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="stSidebarCollapseButton"] svg *,
    section[data-testid="stSidebar"] > div:first-child button:first-child svg,
    section[data-testid="stSidebar"] > div:first-child button:first-child svg * {
        fill:   #f28500 !important;
        stroke: #f28500 !important;
    }

    /* ── Sidebar logo butonu (yalnızca sidebar_logo_btn key'i) ── */
    [data-testid="stSidebar"] .st-key-sidebar_logo_btn .stButton > button {
        background:  transparent !important;
        border:      none        !important;
        box-shadow:  none        !important;
        padding:     .5rem .4rem .2rem !important;
        min-height:  auto !important;
    }
    [data-testid="stSidebar"] .st-key-sidebar_logo_btn .stButton > button p {
        font-size:      1.45rem !important;
        font-weight:    800     !important;
        color:          #F27A1A !important;
        letter-spacing: -.01em  !important;
    }
    [data-testid="stSidebar"] .st-key-sidebar_logo_btn .stButton > button:hover {
        background:    rgba(242,122,26,.1) !important;
        border-radius: 8px !important;
    }

    /* ══════════════════════════════════════════════════════════════════
       MOBILE RESPONSIVE
       Tablet  ≤ 768px : 2-kolonlu grid, küçük font/padding
       Telefon ≤ 480px : tek kolonlu, kompakt layout
    ══════════════════════════════════════════════════════════════════ */

    /* ── Tablet (768px ve altı) ── */
    @media screen and (max-width: 768px) {

        /* ── Sidebar: overlay drawer, ana içerik her zaman tam genişlik ── */
        section[data-testid="stSidebar"] {
            position:   fixed     !important;
            z-index:    1000      !important;
            top:        0         !important;
            left:       0         !important;
            height:     100dvh    !important;
            box-shadow: 4px 0 24px rgba(0,0,0,.5) !important;
        }
        section[data-testid="stMain"] {
            margin-left: 0   !important;
            width:       100vw !important;
        }

        /* Genel padding */
        .block-container {
            padding-left:  0.75rem !important;
            padding-right: 0.75rem !important;
            padding-top:   0.75rem !important;
        }

        /* Başlık şeridi */
        .app-header {
            padding:       0.85rem 1rem !important;
            border-radius: 10px         !important;
            margin-bottom: 0.9rem       !important;
            gap:           0.5rem       !important;
        }
        .app-header span { font-size: 1.5rem !important; }
        .app-header h1   { font-size: 1.2rem !important; }
        .app-header p    { font-size: 0.78rem !important; }

        /* KPI kartları */
        .kpi-card  { padding: 0.8rem 1rem !important; }
        .kpi-value { font-size: 1.5rem   !important; }
        .kpi-label { font-size: 0.7rem   !important; }
        .kpi-sub   { font-size: 0.72rem  !important; }

        /* Bölüm başlığı */
        .section-title {
            font-size:     0.88rem          !important;
            margin:        1rem 0 0.45rem 0 !important;
        }

        /* Bildirim kutuları */
        .info-box, .warn-box, .success-box {
            font-size: 0.82rem !important;
            padding:   0.7rem  !important;
        }

        /* Tab butonları */
        [data-testid="stTabs"] [role="tab"] {
            padding:   .3rem .65rem !important;
            font-size: .78rem       !important;
        }

        /* st.metric */
        [data-testid="stMetric"] {
            padding: 0.65rem 0.85rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }

        /* Dataframe yatay scroll */
        [data-testid="stDataFrame"] {
            overflow-x: auto !important;
        }

        /* ── Sütunları 2'li satıra dönüştür ── */
        section[data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap:       0.5rem !important;
        }
        section[data-testid="stMain"] [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"] {
            min-width: calc(50% - 0.4rem) !important;
            flex:      1 1 calc(50% - 0.4rem) !important;
        }

        /* Mini-dash divider boşlukları */
        .mini-dash-divider {
            margin: 1.1rem 0 0.7rem 0 !important;
        }
    }

    /* ── Telefon (480px ve altı) ── */
    @media screen and (max-width: 480px) {
        .block-container {
            padding-left:  0.5rem !important;
            padding-right: 0.5rem !important;
        }

        .app-header h1 { font-size: 1rem !important; }
        .kpi-value     { font-size: 1.25rem !important; }

        /* Tüm sütunlar tek kolonlu */
        section[data-testid="stMain"] [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"] {
            min-width: 100% !important;
            flex:      1 1 100% !important;
        }

        /* Butonlar tam genişlik + rahat dokunma alanı */
        .stButton > button {
            padding:   0.55rem 0.8rem !important;
            font-size: 0.9rem         !important;
        }

        /* Sidebar nav butonları */
        div[data-testid="stSidebar"] .stButton > button {
            padding:     0.6rem 1rem !important;
            margin-bottom: 0.3rem   !important;
        }

        /* Form submit butonu */
        [data-testid="stFormSubmitButton"] > button {
            padding: 0.6rem !important;
        }

        /* Tab mobilde kaydırılabilsin */
        [data-testid="stTabs"] [role="tablist"] {
            overflow-x: auto  !important;
            flex-wrap:  nowrap !important;
        }

        /* Plotly grafikleri küçük ekranda alt alta */
        .js-plotly-plot { max-height: 280px !important; }

        /* Mini-dash bölüm */
        .mini-dash-divider {
            margin: 0.8rem 0 0.5rem 0 !important;
        }
    }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    defaults = {
        "user": None,
        "page": "dashboard",
        "upload_result": None,
        "active_store_id": None,
        "stores": [],
        "new_user": False,
        "selected_plan": None,
        "plan_period": "m",
        "show_forgot": False,
        "reset_token": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Şifre sıfırlama: URL'de reset_token varsa state'e al ─────────────────
    if not st.session_state.get("reset_token") and not st.session_state.user:
        rt = st.query_params.get("reset_token")
        if rt:
            st.session_state.reset_token = rt

    # ── Oturum kalıcılığı: URL parametresinden otomatik giriş ───────────────
    if st.session_state.user is None:
        tok = st.query_params.get("_rt")
        if tok:
            try:
                user = verify_session_token(tok)
                if user:
                    st.session_state.user = user
            except Exception:
                pass

    # ── Mağaza listesini yükle, yoksa varsayılan oluştur ─────────────────────
    if st.session_state.user is not None and not st.session_state.stores:
        try:
            uid = st.session_state.user["id"]
            stores = get_stores(uid)
            if not stores:
                create_store(uid, st.session_state.user["store_name"])
                stores = get_stores(uid)
            st.session_state.stores = stores
            if stores and st.session_state.active_store_id is None:
                st.session_state.active_store_id = stores[0]["id"]
            # NULL store_id'li siparişleri ilk mağazaya bağla (migration)
            if stores:
                try:
                    link_null_orders(uid, stores[0]["id"])
                except Exception:
                    pass
        except Exception:
            pass


_init_state()


# ─────────────────────────────────────────────────────────────────────────────
# Giriş / Kayıt
# ─────────────────────────────────────────────────────────────────────────────

def _send_telegram(text: str) -> tuple[bool, str]:
    """Telegram bot üzerinden bildirim gönderir. (ok, hata_mesajı) döner."""
    import os, requests as _req
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN") or st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID") or st.secrets.get("TELEGRAM_CHAT_ID", "")
    except Exception:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN tanımlı değil"
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID tanımlı değil"
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
        if r.ok:
            return True, ""
        return False, f"Telegram API hatası: {r.status_code} — {r.text[:200]}"
    except Exception as e:
        return False, str(e)


@st.dialog("✉️ İletişim")
def _contact_dialog() -> None:
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#fff9f0,#fff4e6);
            border:1px solid rgba(242,133,0,.18);border-radius:12px;
            padding:.7rem 1rem;margin-bottom:1rem;
            display:flex;align-items:center;gap:.75rem;">
            <div style="width:36px;height:36px;border-radius:10px;flex-shrink:0;
                background:linear-gradient(135deg,#F28500,#C95A10);
                display:flex;align-items:center;justify-content:center;
                font-size:1rem;box-shadow:0 3px 10px rgba(242,133,0,.28);">✉️</div>
            <div>
                <div style="font-size:.84rem;font-weight:800;color:#0f1a35;margin-bottom:.1rem;">
                    Size nasıl yardımcı olabiliriz?
                </div>
                <div style="font-size:.73rem;color:#6b7280;line-height:1.5;">
                    Ekibimiz <strong style="color:#D46000;">en geç 1 iş günü içinde</strong> dönüş yapar.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("contact_form", border=False):
        name    = st.text_input("Ad Soyad", placeholder="Ahmet Yılmaz")
        company = st.text_input("Mağaza / Şirket Adı", placeholder="Mağazanızın adı")
        email   = st.text_input("E-posta", placeholder="ahmet@magaza.com")
        phone   = st.text_input("Telefon", placeholder="05XX XXX XX XX")
        subject = st.selectbox(
            "Konu",
            ["Plan seçimi ve fiyatlandırma", "Demo talebi", "Teknik entegrasyon",
             "Özel kurumsal teklif", "Fatura ve ödeme", "Diğer"],
        )
        message = st.text_area(
            "Mesajınız",
            placeholder="Trendyol mağazanız hakkında kısa bilgi verin...",
            height=90,
        )
        submitted = st.form_submit_button(
            "Gönder  →", use_container_width=True, type="primary"
        )

    if submitted:
        if not name.strip() or not email.strip() or not message.strip():
            st.error("Ad soyad, e-posta ve mesaj alanları zorunludur.")
        elif "@" not in email or "." not in email.split("@")[-1]:
            st.error("Geçerli bir e-posta adresi girin.")
        else:
            tg_text = (
                "📬 <b>ReOrder — Yeni İletişim Talebi</b>\n\n"
                f"👤 <b>Ad Soyad:</b> {name}\n"
                f"🏪 <b>Mağaza:</b> {company or '—'}\n"
                f"📧 <b>E-posta:</b> {email}\n"
                f"📞 <b>Telefon:</b> {phone or '—'}\n"
                f"📌 <b>Konu:</b> {subject}\n\n"
                f"💬 <b>Mesaj:</b>\n{message}"
            )
            ok, err = _send_telegram(tg_text)
            if ok:
                st.success("✅ Mesajınız alındı! En geç 1 iş günü içinde size dönüş yapacağız.")
            else:
                st.error(f"⚠️ Bildirim gönderilemedi: {err}")


def show_reset_password() -> None:
    """Şifre sıfırlama sayfası — ?reset_token=xxx URL parametresiyle açılır."""
    st.markdown("""
<style>
[data-testid="stSidebar"]{display:none !important;}
[data-testid="stHeader"]{background:transparent !important;}
.block-container{max-width:480px !important;padding:3rem 1.5rem !important;margin:0 auto !important;}
[data-testid="stAppViewContainer"],[data-testid="stMain"],
section[data-testid="stMain"]>div:first-child{background:#f0f4fa !important;}
[data-testid="stTextInput"] label p{color:#374151 !important;font-size:.85rem !important;font-weight:600 !important;}
[data-testid="stTextInput"]>div{background:#fff !important;border:1.5px solid #e2e8f0 !important;border-radius:10px !important;}
[data-testid="stTextInput"]>div:focus-within{border-color:#F28500 !important;box-shadow:0 0 0 3px rgba(242,133,0,.1) !important;}
[data-testid="stTextInput"] input{color:#0f1a35 !important;-webkit-text-fill-color:#0f1a35 !important;background:transparent !important;}
[data-testid="stTextInput"] input::placeholder{color:#9ca3af !important;-webkit-text-fill-color:#9ca3af !important;}
[data-testid="stTextInput"] button svg,[data-testid="stTextInput"] button svg *{fill:#6b7280 !important;}
[data-testid="stFormSubmitButton"]>button{background:linear-gradient(135deg,#F28500,#D46000) !important;color:#fff !important;border:none !important;border-radius:10px !important;font-weight:800 !important;box-shadow:0 4px 16px rgba(242,133,0,.35) !important;}
[data-testid="stFormSubmitButton"]>button:hover{box-shadow:0 6px 22px rgba(242,133,0,.5) !important;}
[data-testid="stAlert"]{background:#fff !important;border-radius:10px !important;color:#374151 !important;}
</style>
""", unsafe_allow_html=True)

    token = st.session_state.get("reset_token", "")

    # Token DB kontrolü
    user = verify_reset_token(token)

    st.markdown(
        """<div style="text-align:center;margin-bottom:1.5rem;">
        <div style="font-size:2rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;">🔄 ReOrder</div>
        <div style="font-size:.8rem;color:#9ca3af;margin-top:.2rem;">Yeni Şifre Belirle</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if not user:
        st.error("❌ Bu bağlantı geçersiz veya süresi dolmuş (1 saat). Lütfen yeni bir sıfırlama talebi oluşturun.")
        if st.button("← Giriş Sayfasına Dön", use_container_width=True):
            st.session_state.reset_token = None
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()
        return

    st.markdown(
        f"<p style='color:#374151;font-size:.88rem;margin-bottom:1rem;'>"
        f"<b>{user['email']}</b> hesabı için yeni şifrenizi belirleyin.</p>",
        unsafe_allow_html=True,
    )

    with st.form("reset_pw_form"):
        new_pw  = st.text_input("Yeni Şifre", type="password",
                                help="En az 8 karakter, 1 rakam içermeli")
        new_pw2 = st.text_input("Yeni Şifre (Tekrar)", type="password")
        sub = st.form_submit_button("🔑 Şifremi Güncelle", use_container_width=True,
                                    type="primary")

    if sub:
        if new_pw != new_pw2:
            st.error("Şifreler eşleşmiyor.")
        else:
            res = reset_password_with_token(token, new_pw)
            if res["success"]:
                st.success("✅ Şifreniz başarıyla güncellendi! Şimdi giriş yapabilirsiniz.")
                st.session_state.reset_token = None
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.balloons()
                import time as _time
                _time.sleep(2)
                st.rerun()
            else:
                st.error(res["error"])


def show_auth() -> None:  # noqa: C901
    import streamlit.components.v1 as _cmp

    # ── Page-level CSS ─────────────────────────────────────────────────────────
    st.markdown("""
<style>
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section[data-testid="stMain"] > div:first-child {
    background: #f0f4fa !important;
    min-height: 100vh !important;
}
body,html{overflow-x:hidden;}
[data-testid="stSidebar"]{display:none !important;}
[data-testid="stHeader"]{background:transparent !important;}
.block-container{padding:0 !important;max-width:100% !important;background:transparent !important;}
[data-testid="stHorizontalBlock"]{gap:0 !important;align-items:stretch !important;min-height:100vh !important;}
/* Left col */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child{background:#f0f4fa !important;}
/* Right col — dark navy */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"]{
    background:linear-gradient(160deg,#1a2744 0%,#0f1a35 55%,#162040 100%) !important;
    min-height:100vh !important;
    padding:2.2rem 2rem 2rem !important;
    display:flex !important; flex-direction:column !important;
    align-items:center !important; justify-content:center !important;
    position:relative !important; overflow:hidden !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"]::before{
    content:"";position:absolute;top:-30%;left:-20%;width:80%;height:60%;border-radius:50%;
    background:radial-gradient(ellipse,rgba(242,133,0,.1) 0%,transparent 65%);pointer-events:none;
}
/* Tabs */
[data-testid="stTabs"] [role="tablist"]{border-bottom:1px solid rgba(242,133,0,.22) !important;gap:5px !important;}
[data-testid="stTabs"] [role="tab"]{
    background:rgba(255,255,255,.05) !important;color:rgba(255,255,255,.35) !important;
    font-weight:600 !important;font-size:.84rem !important;
    border-radius:8px 8px 0 0 !important;
    border:1px solid rgba(255,255,255,.07) !important;border-bottom:none !important;
    padding:.43rem 1.1rem !important;transition:background .18s,color .18s !important;
}
[data-testid="stTabs"] [role="tab"]:hover{background:rgba(242,133,0,.1) !important;color:rgba(255,255,255,.65) !important;}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{
    background:linear-gradient(135deg,#F28500,#D46000) !important;color:#fff !important;
    border-color:transparent !important;box-shadow:0 -2px 10px rgba(242,133,0,.3) !important;
}
[data-testid="stTabsContent"]{background:transparent !important;}
/* Inputs */
[data-testid="stTextInput"] label p{color:rgba(180,210,230,.72) !important;font-size:.79rem !important;font-weight:600 !important;}
[data-testid="stTextInput"] > div{
    background:rgba(255,255,255,.07) !important;border:1.5px solid rgba(255,255,255,.12) !important;
    border-radius:11px !important;transition:border-color .2s,box-shadow .2s !important;overflow:hidden !important;
}
[data-testid="stTextInput"] > div:focus-within{
    border-color:rgba(242,133,0,.58) !important;box-shadow:0 0 0 3px rgba(242,133,0,.11) !important;
}
[data-testid="stTextInput"] > div > div,
[data-testid="stTextInput"] > div > div > div{background:transparent !important;}
[data-testid="stTextInput"] input{background:transparent !important;color:#fff !important;font-size:.89rem !important;-webkit-text-fill-color:#fff !important;}
[data-testid="stTextInput"] input::placeholder{color:rgba(255,255,255,.2) !important;-webkit-text-fill-color:rgba(255,255,255,.2) !important;}
[data-testid="stTextInput"] button{background:transparent !important;border:none !important;}
[data-testid="stTextInput"] button svg,[data-testid="stTextInput"] button svg *{fill:rgba(255,255,255,.38) !important;}
/* Submit button */
[data-testid="stFormSubmitButton"] > button{
    background:linear-gradient(135deg,#F28500,#D46000) !important;color:#fff !important;
    border:none !important;border-radius:11px !important;font-weight:800 !important;
    font-size:.91rem !important;letter-spacing:.04em !important;text-transform:uppercase !important;
    box-shadow:0 4px 18px rgba(242,133,0,.44) !important;padding:.8rem !important;
    transition:transform .15s,box-shadow .15s,filter .15s !important;
}
[data-testid="stFormSubmitButton"] > button:hover{transform:translateY(-2px) !important;box-shadow:0 8px 26px rgba(242,133,0,.55) !important;filter:brightness(1.06) !important;}
[data-testid="stFormSubmitButton"] > button:active{transform:translateY(0) !important;}
/* Alert */
[data-testid="stAlert"]{background:rgba(10,37,51,.55) !important;border:1px solid rgba(242,133,0,.25) !important;border-radius:10px !important;color:#dff0f8 !important;}
/* İletişime Geç butonu (sağ panel) */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child button:not([data-testid="stFormSubmitButton"] > button):not([role="tab"]){
    background:rgba(255,255,255,.06) !important;color:rgba(255,255,255,.55) !important;
    border:1.5px solid rgba(255,255,255,.1) !important;border-radius:11px !important;
    font-size:.83rem !important;font-weight:600 !important;
    transition:background .18s,border-color .18s,color .18s !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child button:not([data-testid="stFormSubmitButton"] > button):not([role="tab"]):hover{
    background:rgba(242,133,0,.1) !important;border-color:rgba(242,133,0,.35) !important;
    color:rgba(255,255,255,.85) !important;
}
/* ── İletişim Formu Dialog ── */
[data-testid="stDialog"] > div > div{
    background:#ffffff !important;
    border-radius:20px !important;
    border:1px solid #e8edf5 !important;
    box-shadow:0 24px 64px rgba(15,26,53,.14) !important;
    padding:0 !important;
    overflow:hidden !important;
}
/* Dialog kapat butonu */
[data-testid="stDialog"] button[aria-label="Close"]{
    background:rgba(0,0,0,.04) !important;border-radius:8px !important;
    color:#6b7280 !important;border:none !important;
    transition:background .15s !important;
}
[data-testid="stDialog"] button[aria-label="Close"]:hover{background:rgba(0,0,0,.08) !important;}
/* ── Dialog genel ── */
[data-testid="stDialog"] [data-testid="stVerticalBlock"]{
    padding:.8rem 1.2rem .8rem !important;gap:.35rem !important;
}
[data-testid="stDialog"] [data-testid="stVerticalBlock"] > div{
    margin-bottom:0 !important;padding-bottom:0 !important;
}
[data-testid="stDialog"] [data-testid="stHorizontalBlock"]{
    gap:.5rem !important;margin-bottom:0 !important;
}
/* Labels */
[data-testid="stDialog"] label p{
    color:#374151 !important;font-size:.76rem !important;
    font-weight:700 !important;margin-bottom:.18rem !important;
}
/* Text input wrapper */
[data-testid="stDialog"] [data-testid="stTextInput"] > div{
    background:#f8faff !important;border:1.5px solid #e2e8f0 !important;
    border-radius:9px !important;min-height:0 !important;height:auto !important;
    padding:0 !important;transition:border-color .18s,box-shadow .18s !important;
    overflow:hidden !important;
}
[data-testid="stDialog"] [data-testid="stTextInput"] > div:focus-within{
    border-color:#F28500 !important;box-shadow:0 0 0 3px rgba(242,133,0,.09) !important;
    background:#fff !important;
}
/* Input element */
[data-testid="stDialog"] [data-testid="stTextInput"] input{
    padding:.42rem .75rem !important;height:38px !important;
    color:#0f1a35 !important;-webkit-text-fill-color:#0f1a35 !important;
    font-size:.84rem !important;background:transparent !important;
}
[data-testid="stDialog"] [data-testid="stTextInput"] input::placeholder{
    color:#b0b8c8 !important;-webkit-text-fill-color:#b0b8c8 !important;
}
/* Textarea */
[data-testid="stDialog"] [data-testid="stTextArea"] > div{
    background:#f8faff !important;border:1.5px solid #e2e8f0 !important;
    border-radius:9px !important;padding:0 !important;
    transition:border-color .18s,box-shadow .18s !important;
}
[data-testid="stDialog"] [data-testid="stTextArea"] > div:focus-within{
    border-color:#F28500 !important;box-shadow:0 0 0 3px rgba(242,133,0,.09) !important;
    background:#fff !important;
}
[data-testid="stDialog"] [data-testid="stTextArea"] textarea{
    padding:.42rem .75rem !important;color:#0f1a35 !important;font-size:.84rem !important;
}
[data-testid="stDialog"] [data-testid="stTextArea"] textarea::placeholder{color:#b0b8c8 !important;}
/* Selectbox */
[data-testid="stDialog"] [data-testid="stSelectbox"] > div > div{
    background:#f8faff !important;border:1.5px solid #e2e8f0 !important;
    border-radius:9px !important;
}
[data-testid="stDialog"] [data-testid="stSelectbox"] > div > div:focus-within{
    border-color:#F28500 !important;box-shadow:0 0 0 3px rgba(242,133,0,.09) !important;
}
/* Submit butonu */
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] > button{
    background:linear-gradient(135deg,#F28500,#D46000) !important;
    color:#fff !important;border:none !important;border-radius:9px !important;
    font-weight:800 !important;font-size:.86rem !important;
    box-shadow:0 4px 14px rgba(242,133,0,.38) !important;
    padding:.55rem 1rem !important;
    transition:transform .15s,box-shadow .15s !important;
}
[data-testid="stDialog"] [data-testid="stFormSubmitButton"] > button:hover{
    transform:translateY(-1px) !important;box-shadow:0 7px 22px rgba(242,133,0,.5) !important;
}
/* Alert */
[data-testid="stDialog"] [data-testid="stAlert"]{
    border-radius:9px !important;font-size:.8rem !important;padding:.5rem .75rem !important;
}
/* Tooltip */
[data-testid="stTooltipIcon"] svg,[data-testid="stTooltipIcon"] svg *{fill:rgba(242,133,0,.8) !important;}
/* Mobile header — hidden on desktop */
.ro-mob-hdr{display:none;}
/* Footer pill */
.ro-login-footer{
    position:fixed;bottom:15px;left:50%;transform:translateX(-50%);
    display:inline-flex;align-items:center;gap:.5rem;
    background:rgba(10,20,40,.75);backdrop-filter:blur(10px);
    border:1px solid rgba(255,255,255,.07);border-radius:40px;
    padding:.33rem 1.1rem;font-size:.68rem;color:rgba(255,255,255,.35);
    white-space:nowrap;z-index:9999;pointer-events:none;letter-spacing:.03em;
}
.ro-login-footer a{color:rgba(255,255,255,.35) !important;text-decoration:none !important;pointer-events:all;transition:color .2s;}
.ro-login-footer a:hover{color:#F28500 !important;}
.ro-sep{opacity:.28;}
/* ── MOBILE ≤ 768px ── */
@media (max-width:768px){
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child{display:none !important;}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child{min-width:100% !important;flex:1 1 100% !important;}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"]{padding:1.8rem 1.2rem 2rem !important;justify-content:flex-start !important;}
    .ro-mob-hdr{display:block !important;}
    .block-container{padding-left:0 !important;padding-right:0 !important;}
    .ro-login-footer{font-size:.6rem !important;padding:.28rem .85rem !important;}
    /* Mobil marketing bloğu görünür */
    .ro-mob-marketing{display:block !important;}
}
@media (max-width:400px){.ro-login-footer{display:none !important;}}
</style>
""", unsafe_allow_html=True)

    # ── Mobile-only top header ─────────────────────────────────────────────────
    st.markdown("""
<div class="ro-mob-hdr" style="
    background:linear-gradient(135deg,#fff9f0,#ffffff,#f0f7ff);
    padding:1.4rem 1.4rem 1.1rem;border-bottom:1px solid #e8edf5;text-align:center;">
  <div style="display:flex;align-items:center;justify-content:center;gap:.65rem;margin-bottom:.6rem;">
    <div style="width:40px;height:40px;border-radius:11px;
        background:linear-gradient(135deg,#F28500,#C95A10);
        display:flex;align-items:center;justify-content:center;
        font-size:1.15rem;box-shadow:0 4px 14px rgba(242,133,0,.35);">&#x1F504;</div>
    <div>
      <div style="font-size:1.2rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;">ReOrder</div>
      <div style="font-size:.63rem;color:#9ca3af;">Trendyol Retention Platformu</div>
    </div>
  </div>
  <div style="font-size:.82rem;font-weight:600;color:#374151;margin-bottom:.7rem;">
    M&#252;&#351;terini Geri Kazan, Gelirini Art&#305;r
  </div>
  <div style="display:flex;justify-content:center;flex-wrap:wrap;gap:.4rem;">
    <span style="background:#fff0e0;border:1px solid rgba(242,133,0,.3);border-radius:20px;padding:.15rem .6rem;font-size:.64rem;font-weight:700;color:#d46000;">+34% Retention</span>
    <span style="background:#f0fdf4;border:1px solid rgba(16,185,129,.3);border-radius:20px;padding:.15rem .6rem;font-size:.64rem;font-weight:700;color:#059669;">-41% Churn</span>
    <span style="background:#eff6ff;border:1px solid rgba(59,130,246,.2);border-radius:20px;padding:.15rem .6rem;font-size:.64rem;font-weight:700;color:#1d4ed8;">3.2x LTV</span>
    <span style="background:#f0fdfa;border:1px solid rgba(20,184,166,.2);border-radius:20px;padding:.15rem .6rem;font-size:.64rem;font-weight:700;color:#0f766e;">150+ Ma&#287;aza</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Columns ───────────────────────────────────────────────────────────────
    col_l, col_c = st.columns([1.7, 1])

    with col_l:
        _left_html = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
html,body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f4fa;color:#0f1a35;overflow-x:hidden;}
.hero{background:linear-gradient(135deg,#fff9f0 0%,#ffffff 50%,#f0f7ff 100%);border-bottom:1px solid #e8edf5;padding:1.8rem 2rem 1.5rem;position:relative;overflow:hidden;}
.hero::before{content:"";position:absolute;top:-50px;right:-50px;width:200px;height:200px;border-radius:50%;background:radial-gradient(ellipse,rgba(242,133,0,.1) 0%,transparent 65%);}
.logo-row{display:flex;align-items:center;gap:.7rem;margin-bottom:1.4rem;}
.logo-icon{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,#F28500,#C95A10);display:flex;align-items:center;justify-content:center;font-size:1.2rem;box-shadow:0 5px 16px rgba(242,133,0,.35);flex-shrink:0;}
.logo-name{font-size:1.3rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;}
.logo-tag{font-size:.63rem;color:#9ca3af;margin-top:.1rem;}
.hero-pill{display:inline-flex;align-items:center;gap:.35rem;background:#fff0e0;border:1px solid rgba(242,133,0,.3);border-radius:20px;padding:.2rem .7rem;font-size:.67rem;font-weight:700;color:#c05c00;letter-spacing:.05em;margin-bottom:.85rem;}
.hero-pill::before{content:"";width:5px;height:5px;border-radius:50%;background:#F28500;animation:blink 2s infinite;flex-shrink:0;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.3;}}
.hero-h1{font-size:1.85rem;font-weight:900;color:#0f1a35;line-height:1.15;letter-spacing:-.03em;margin-bottom:.55rem;}
.hero-h1 em{font-style:normal;background:linear-gradient(135deg,#F28500,#e55f00);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.hero-sub{font-size:.81rem;color:#6b7280;line-height:1.65;margin-bottom:1.25rem;max-width:490px;}
.stats{display:flex;background:#fff;border:1px solid #e8edf5;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.04);}
.stat{flex:1;padding:.7rem .9rem;border-right:1px solid #f0f2f7;transition:background .15s;}
.stat:last-child{border-right:none;}
.stat:hover{background:#fafbff;}
.sv{font-size:1.2rem;font-weight:900;color:#0f1a35;line-height:1;}
.sv em{color:#F28500;font-style:normal;}
.sl{font-size:.57rem;color:#9ca3af;text-transform:uppercase;letter-spacing:.07em;margin-top:.18rem;}
.live-bar{background:#fff;border-bottom:1px solid #e8edf5;padding:.55rem 2rem;display:flex;align-items:center;gap:1.2rem;overflow:hidden;}
.live-badge{display:inline-flex;align-items:center;gap:.35rem;background:#f0fdf4;border:1px solid rgba(16,185,129,.28);border-radius:20px;padding:.18rem .65rem;font-size:.66rem;font-weight:700;color:#059669;flex-shrink:0;white-space:nowrap;}
.live-badge::before{content:"";width:6px;height:6px;border-radius:50%;background:#10B981;animation:blink 1.8s infinite;flex-shrink:0;}
.ticker-wrap{flex:1;overflow:hidden;position:relative;}
.ticker-wrap::before{content:"";position:absolute;left:0;top:0;bottom:0;width:32px;background:linear-gradient(to right,#fff,transparent);z-index:1;}
.ticker-wrap::after{content:"";position:absolute;right:0;top:0;bottom:0;width:32px;background:linear-gradient(to left,#fff,transparent);z-index:1;}
.ticker{display:flex;animation:ticker 42s linear infinite;white-space:nowrap;}
.ticker:hover{animation-play-state:paused;}
.ti{font-size:.69rem;color:#6b7280;padding:0 2rem;}
.ti strong{color:#374151;font-weight:600;}
@keyframes ticker{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.features{padding:1.5rem 2rem 0;}
.sec-tag{font-size:.62rem;font-weight:700;color:#F28500;text-transform:uppercase;letter-spacing:.12em;margin-bottom:.35rem;display:flex;align-items:center;gap:.45rem;}
.sec-tag::before{content:"";display:inline-block;width:16px;height:2px;background:#F28500;border-radius:1px;}
.sec-title{font-size:1.22rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;margin-bottom:.28rem;}
.sec-sub{font-size:.79rem;color:#9ca3af;line-height:1.6;margin-bottom:1.1rem;}
.feat-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;}
.feat{background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:1rem 1.1rem;box-shadow:0 1px 4px rgba(0,0,0,.04);transition:all .22s;cursor:default;position:relative;overflow:hidden;}
.feat:hover{border-color:rgba(242,133,0,.25);box-shadow:0 6px 20px rgba(0,0,0,.09);transform:translateY(-2px);}
.feat-top{display:flex;align-items:center;gap:.55rem;margin-bottom:.4rem;}
.fi{width:35px;height:35px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:.95rem;flex-shrink:0;}
.fi-or{background:#fff4e6;border:1px solid rgba(242,133,0,.2);}
.fi-rd{background:#fff0f0;border:1px solid rgba(239,68,68,.18);}
.fi-bl{background:#eff6ff;border:1px solid rgba(59,130,246,.2);}
.fi-gr{background:#f0fdf4;border:1px solid rgba(16,185,129,.2);}
.fi-pu{background:#faf5ff;border:1px solid rgba(139,92,246,.18);}
.fi-te{background:#f0fdfa;border:1px solid rgba(20,184,166,.2);}
.ft{font-size:.81rem;font-weight:700;color:#0f1a35;}
.fd{font-size:.72rem;color:#6b7280;line-height:1.6;}
.ftags{display:flex;flex-wrap:wrap;gap:.25rem;margin-top:.48rem;}
.tag{font-size:.58rem;font-weight:600;border-radius:20px;padding:.1rem .48rem;}
.to{background:#fff4e6;color:#c05c00;border:1px solid rgba(242,133,0,.2);}
.tb{background:#eff6ff;color:#1d4ed8;border:1px solid rgba(59,130,246,.2);}
.tg{background:#f0fdf4;color:#065f46;border:1px solid rgba(16,185,129,.2);}
.tp{background:#faf5ff;color:#6d28d9;border:1px solid rgba(139,92,246,.2);}
.tt{background:#f0fdfa;color:#0f766e;border:1px solid rgba(20,184,166,.2);}
.soc-strip{margin:1.2rem 2rem 0;background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.8rem 1.1rem;display:flex;align-items:center;gap:1rem;box-shadow:0 1px 4px rgba(0,0,0,.04);}
.soc-avatars{display:flex;align-items:center;}
.soc-av{width:30px;height:30px;border-radius:50%;border:2px solid #fff;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;color:#fff;margin-left:-8px;flex-shrink:0;}
.soc-av:first-child{margin-left:0;}
.soc-av-more{background:#e8edf5;color:#6b7280;font-size:.6rem;font-weight:700;width:30px;height:30px;border-radius:50%;border:2px solid #fff;display:flex;align-items:center;justify-content:center;margin-left:-8px;}
.soc-text{flex:1;font-size:.76rem;color:#374151;}
.soc-text strong{font-weight:700;color:#0f1a35;}
.soc-rating{display:flex;align-items:center;gap:.25rem;flex-shrink:0;}
.stars{color:#F28500;font-size:.75rem;}
.rating-val{font-size:.72rem;font-weight:700;color:#0f1a35;}
.pricing{padding:1.4rem 2rem 2rem;}
.period-toggle{display:flex;background:#fff;border:1px solid #e8edf5;border-radius:9px;padding:3px;gap:3px;box-shadow:0 1px 4px rgba(0,0,0,.04);margin-bottom:1.1rem;max-width:fit-content;}
.pt{padding:.36rem .88rem;border-radius:7px;border:none;background:transparent;color:#9ca3af;font-size:.74rem;font-weight:600;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:.32rem;}
.pt.on{background:#F28500;color:#fff;box-shadow:0 2px 8px rgba(242,133,0,.35);}
.sb{background:rgba(16,185,129,.1);color:#059669;border:1px solid rgba(16,185,129,.22);border-radius:20px;font-size:.54rem;font-weight:700;padding:.05rem .38rem;}
.pt.on .sb{background:rgba(255,255,255,.22);color:#fff;border-color:rgba(255,255,255,.28);}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;}
.plan{background:#fff;border:1.5px solid #e8edf5;border-radius:14px;padding:1.15rem 1.05rem;position:relative;overflow:hidden;transition:all .22s;box-shadow:0 1px 4px rgba(0,0,0,.04);}
.plan:hover{box-shadow:0 6px 20px rgba(0,0,0,.09);transform:translateY(-2px);}
.plan.pop{background:linear-gradient(135deg,#fff9f0,#fff);border-color:#F28500;box-shadow:0 4px 18px rgba(242,133,0,.14);}
.plan.pop:hover{box-shadow:0 10px 28px rgba(242,133,0,.2);}
.pr{position:absolute;top:0;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.51rem;font-weight:800;letter-spacing:.08em;padding:.22rem 1rem;border-radius:0 0 9px 9px;}
.pn{font-size:.64rem;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.48rem;}
.plan.pop .pn{margin-top:1.05rem;}
.pp{display:flex;align-items:baseline;gap:.12rem;}
.pc{font-size:.84rem;font-weight:700;color:#6b7280;}
.pa{font-size:1.75rem;font-weight:900;color:#0f1a35;line-height:1;}
.plan.pop .pa{color:#F28500;}
.pper{font-size:.63rem;color:#9ca3af;}
.pnote{font-size:.6rem;color:#9ca3af;margin-top:.08rem;}
.psave{font-size:.61rem;font-weight:700;color:#059669;background:#f0fdf4;border:1px solid rgba(16,185,129,.2);border-radius:20px;padding:.09rem .42rem;display:inline-block;margin-top:.28rem;margin-bottom:.65rem;}
.psave.h{opacity:0;pointer-events:none;}
.pd{height:1px;background:#f0f2f7;margin:.65rem 0;}
.pf{display:flex;align-items:center;gap:.42rem;font-size:.71rem;color:#374151;margin-bottom:.32rem;}
.pok{width:14px;height:14px;border-radius:50%;background:#f0fdf4;border:1px solid rgba(16,185,129,.3);display:flex;align-items:center;justify-content:center;font-size:.48rem;color:#059669;flex-shrink:0;}
.pno{width:14px;height:14px;border-radius:50%;background:#f9fafb;border:1px solid #e5e7eb;display:flex;align-items:center;justify-content:center;font-size:.48rem;color:#d1d5db;flex-shrink:0;}
.dim{color:#c4c9d4;}
.pcta{width:100%;padding:.62rem;border-radius:9px;font-size:.81rem;font-weight:700;cursor:pointer;transition:all .15s;border:none;margin-top:.55rem;}
.cout{background:#f9fafb;color:#374151;border:1.5px solid #e5e7eb;}
.cout:hover{background:#f3f4f6;}
.cmain{background:linear-gradient(135deg,#F28500,#D46000);color:#fff;box-shadow:0 3px 12px rgba(242,133,0,.4);}
.cmain:hover{box-shadow:0 6px 20px rgba(242,133,0,.5);}
.pv{display:none;}.pv.s{display:inline;}
</style>
</head>
<body>
<!-- HERO -->
<div class="hero">
  <div class="logo-row">
    <div class="logo-icon">&#x1F504;</div>
    <div><div class="logo-name">ReOrder</div><div class="logo-tag">Trendyol Retention &amp; Analitik Platformu</div></div>
  </div>
  <div class="hero-pill">Trendyol Ma&#287;azalar&#305; &#304;&#231;in Geli&#351;tirildi</div>
  <h1 class="hero-h1">M&#252;&#351;terini Geri Kazan.<br><em>Gelirini Art&#305;r.</em></h1>
  <p class="hero-sub">Cohort retention, RFM segmentasyon, churn tahmini ve profesyonel PDF raporlama &mdash; tek platformda.</p>
  <div class="stats">
    <div class="stat"><div class="sv">+<em>34</em>%</div><div class="sl">Retention Art&#305;&#351;&#305;</div></div>
    <div class="stat"><div class="sv"><em>3.2</em>x</div><div class="sl">LTV Kazan&#305;m&#305;</div></div>
    <div class="stat"><div class="sv">&minus;<em>41</em>%</div><div class="sl">Churn Azalmas&#305;</div></div>
    <div class="stat"><div class="sv"><em>150</em>+</div><div class="sl">Aktif Ma&#287;aza</div></div>
  </div>
</div>
<!-- LIVE BAR -->
<div class="live-bar">
  <div class="live-badge">&#129309; 150+ &#304;&#351; Orta&#287;&#305;m&#305;z</div>
  <div class="ticker-wrap">
    <div class="ticker">
      <span class="ti"><strong>KozmikModa</strong></span>
      <span class="ti"><strong>TechnoMart</strong></span>
      <span class="ti"><strong>SportStyle</strong></span>
      <span class="ti"><strong>PetShopTR</strong></span>
      <span class="ti"><strong>GiyimHane</strong></span>
      <span class="ti"><strong>ElektroStore</strong></span>
      <span class="ti"><strong>ModaDepom</strong></span>
      <span class="ti"><strong>AyakkabıDünyası</strong></span>
      <span class="ti"><strong>BebekSepeti</strong></span>
      <span class="ti"><strong>MobilyaPlus</strong></span>
      <span class="ti"><strong>KozmetikHane</strong></span>
      <span class="ti"><strong>SporZone</strong></span>
      <span class="ti"><strong>TeknoGadget</strong></span>
      <span class="ti"><strong>AntikaVista</strong></span>
      <span class="ti"><strong>EvDekorasyon</strong></span>
      <span class="ti"><strong>BahçeMarket</strong></span>
      <span class="ti"><strong>OyuncakDiyarı</strong></span>
      <span class="ti"><strong>SağlıkMağaza</strong></span>
      <span class="ti"><strong>KitapYurdu</strong></span>
      <span class="ti"><strong>ZücaciyeDepot</strong></span>
      <span class="ti"><strong>AydınlatmaEvi</strong></span>
      <span class="ti"><strong>ButikFashion</strong></span>
      <span class="ti"><strong>OtomobilPlus</strong></span>
      <span class="ti"><strong>MobiliaShop</strong></span>
      <span class="ti"><strong>YaşamMarket</strong></span>
      <span class="ti"><strong>TrendGiyim</strong></span>
      <span class="ti"><strong>PazarYeri</strong></span>
      <span class="ti"><strong>AnatoliaStore</strong></span>
      <span class="ti"><strong>EkoButik</strong></span>
      <span class="ti"><strong>DijiMarket</strong></span>
      <span class="ti"><strong>LüksMode</strong></span>
      <span class="ti"><strong>AtölyeShop</strong></span>
      <span class="ti"><strong>FırçaStüdyo</strong></span>
      <span class="ti"><strong>TabiatEv</strong></span>
      <span class="ti"><strong>YenilikçiTek</strong></span>
      <span class="ti"><strong>MegaMağaza</strong></span>
      <span class="ti"><strong>NaturalLife</strong></span>
      <span class="ti"><strong>UstaElektr</strong></span>
      <span class="ti"><strong>SezonBoutique</strong></span>
      <span class="ti"><strong>GüncelShop</strong></span>
      <span class="ti"><strong>KozmikModa</strong></span>
      <span class="ti"><strong>TechnoMart</strong></span>
      <span class="ti"><strong>SportStyle</strong></span>
      <span class="ti"><strong>PetShopTR</strong></span>
      <span class="ti"><strong>GiyimHane</strong></span>
      <span class="ti"><strong>ElektroStore</strong></span>
      <span class="ti"><strong>ModaDepom</strong></span>
      <span class="ti"><strong>AyakkabıDünyası</strong></span>
      <span class="ti"><strong>BebekSepeti</strong></span>
      <span class="ti"><strong>MobilyaPlus</strong></span>
      <span class="ti"><strong>KozmetikHane</strong></span>
      <span class="ti"><strong>SporZone</strong></span>
      <span class="ti"><strong>TeknoGadget</strong></span>
      <span class="ti"><strong>AntikaVista</strong></span>
      <span class="ti"><strong>EvDekorasyon</strong></span>
      <span class="ti"><strong>BahçeMarket</strong></span>
      <span class="ti"><strong>OyuncakDiyarı</strong></span>
      <span class="ti"><strong>SağlıkMağaza</strong></span>
      <span class="ti"><strong>KitapYurdu</strong></span>
      <span class="ti"><strong>ZücaciyeDepot</strong></span>
      <span class="ti"><strong>AydınlatmaEvi</strong></span>
      <span class="ti"><strong>ButikFashion</strong></span>
      <span class="ti"><strong>OtomobilPlus</strong></span>
      <span class="ti"><strong>MobiliaShop</strong></span>
      <span class="ti"><strong>YaşamMarket</strong></span>
      <span class="ti"><strong>TrendGiyim</strong></span>
      <span class="ti"><strong>PazarYeri</strong></span>
      <span class="ti"><strong>AnatoliaStore</strong></span>
      <span class="ti"><strong>EkoButik</strong></span>
      <span class="ti"><strong>DijiMarket</strong></span>
      <span class="ti"><strong>LüksMode</strong></span>
      <span class="ti"><strong>AtölyeShop</strong></span>
      <span class="ti"><strong>FırçaStüdyo</strong></span>
      <span class="ti"><strong>TabiatEv</strong></span>
      <span class="ti"><strong>YenilikçiTek</strong></span>
      <span class="ti"><strong>MegaMağaza</strong></span>
      <span class="ti"><strong>NaturalLife</strong></span>
      <span class="ti"><strong>UstaElektr</strong></span>
      <span class="ti"><strong>SezonBoutique</strong></span>
      <span class="ti"><strong>GüncelShop</strong></span>
    </div>
  </div>
</div>
<!-- FEATURES -->
<div class="features">
  <div class="sec-tag">&#214;zellikler</div>
  <div class="sec-title">Her &#351;ey tek yerden</div>
  <div class="sec-sub">Trendyol ma&#287;azan&#305; b&#252;y&#252;tmek i&#231;in ihtiya&#231; duydu&#287;un t&#252;m ara&#231;lar. <span style="background:linear-gradient(135deg,#F28500,#D46000);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:700;">7 yeni &#246;zellik eklendi!</span></div>
  <div class="feat-grid">
    <div class="feat">
      <div class="feat-top"><div class="fi fi-or">&#128202;</div><div class="ft">Anl&#305;k Dashboard</div></div>
      <div class="fd">G&#252;nl&#252;k gelir, sipari&#351; ve aktif m&#252;&#351;teriyi ger&#231;ek zamanl&#305; izle. Otomatik API senkronizasyonu.</div>
      <div class="ftags"><span class="tag to">Ger&#231;ek Zamanl&#305;</span><span class="tag tb">Grafik</span></div>
    </div>
    <div class="feat">
      <div class="feat-top"><div class="fi fi-rd">&#128293;</div><div class="ft">Cohort Retention</div></div>
      <div class="fd">Hangi m&#252;&#351;teri geri d&#246;nd&#252;? Renk kodlu heatmap ile d&#252;&#351;&#252;&#351; noktalar&#305;n&#305; g&#246;r.</div>
      <div class="ftags"><span class="tag to">Heatmap</span><span class="tag tg">Ayl&#305;k Kohort</span></div>
    </div>
    <div class="feat">
      <div class="feat-top"><div class="fi fi-bl">&#128101;</div><div class="ft">RFM &amp; Churn Skoru</div></div>
      <div class="fd">0-100 churn riski, 4 segment: Sad&#305;k, Potansiyel, Uyku, Kay&#305;p.</div>
      <div class="ftags"><span class="tag tb">Churn 0-100</span><span class="tag tp">RFM</span><span class="tag tg">LTV</span></div>
    </div>
    <div class="feat">
      <div class="feat-top"><div class="fi fi-gr">&#128231;</div><div class="ft">E-posta Kampanya</div></div>
      <div class="fd">Segmente &#246;zel &#351;ablonlarla m&#252;&#351;terilerini geri &#231;ek. SMTP entegrasyonu ile g&#246;nder.</div>
      <div class="ftags"><span class="tag tg">SMTP</span><span class="tag to">&#350;ablonlar</span></div>
    </div>
    <div class="feat">
      <div class="feat-top"><div class="fi fi-pu">&#128196;</div><div class="ft">PDF Rapor</div></div>
      <div class="fd">3 sayfalık markal&#305; analitik raporu tek t&#305;kla olu&#351;tur. Sunum kalitesinde.</div>
      <div class="ftags"><span class="tag tp">3 Sayfa</span><span class="tag to">Tek T&#305;k</span></div>
    </div>
    <div class="feat">
      <div class="feat-top"><div class="fi fi-te">&#127978;</div><div class="ft">&#199;oklu Ma&#287;aza</div></div>
      <div class="fd">Birden fazla Trendyol ma&#287;azan&#305; tek hesaptan y&#246;net. Ba&#287;&#305;ms&#305;z API.</div>
      <div class="ftags"><span class="tag tt">&#199;oklu Ma&#287;aza</span><span class="tag tb">API</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-or">&#128302;</div><div class="ft">Gelir Tahmini</div></div>
      <div class="fd">Sonraki 30&#8211;180 g&#252;n&#252;n gelirini lineer trend analizi ile tahmin et. G&#252;ven aral&#305;kl&#305; grafik.</div>
      <div class="ftags"><span class="tag to">AI Tahmin</span><span class="tag tb">Pro+</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-bl">&#128279;</div><div class="ft">Cross-Sell Matrisi</div></div>
      <div class="fd">Birlikte sat&#305;n al&#305;nan &#252;r&#252;n &#231;iftleri. G&#252;ven skoru ve lift analizi ile en iyi &#246;neri f&#305;rsatlar&#305;n&#305; bul.</div>
      <div class="ftags"><span class="tag tp">Cross-Sell</span><span class="tag tb">Pro+</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-gr">&#128197;</div><div class="ft">D&#246;nem Kar&#351;&#305;la&#351;t&#305;rmas&#305;</div></div>
      <div class="fd">Bu ay vs ge&#231;en ay, bu y&#305;l vs ge&#231;en y&#305;l. Gelir, sipari&#351; ve m&#252;&#351;teri de&#287;i&#351;imini g&#246;r.</div>
      <div class="ftags"><span class="tag tg">Trendler</span><span class="tag to">Grafik</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-rd">&#128276;</div><div class="ft">Anl&#305;k Bildirimler</div></div>
      <div class="fd">Gelir d&#252;&#351;&#252;&#351;&#252;, ani art&#305;&#351; veya b&#252;y&#252;k sipari&#351; geldi&#287;inde otomatik uyar&#305; al.</div>
      <div class="ftags"><span class="tag to">Anomali</span><span class="tag tg">Otomatik</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-pu">&#127919;</div><div class="ft">Aksiyon &#214;nerileri</div></div>
      <div class="fd">Her segment i&#231;in &#246;ncelikli aksiyonlar: hangi m&#252;&#351;teriye ne zaman ne yap? Beklenen etki hesab&#305;.</div>
      <div class="ftags"><span class="tag tp">Yapay Zeka</span><span class="tag to">&#214;neriler</span></div>
    </div>
    <div class="feat" style="border-color:rgba(242,133,0,.3);background:linear-gradient(135deg,#fffbf5,#fff);">
      <div style="position:absolute;top:-1px;right:10px;background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.18rem .55rem;border-radius:0 0 7px 7px;">YEN&#304;</div>
      <div class="feat-top"><div class="fi fi-te">&#128337;</div><div class="ft">Haftal&#305;k Rapor</div></div>
      <div class="fd">Her Pazartesi sabah&#305; m&#228;&#287;azan&#305;n&#305;n &#246;zeti e-posta ile gelsin. Hi&#231;bir metri&#287;i ka&#231;&#305;rma.</div>
      <div class="ftags"><span class="tag tt">Otomatik</span><span class="tag tb">Pro+</span></div>
    </div>
  </div>
</div>
<!-- SOCIAL PROOF STRIP -->
<div class="soc-strip">
  <div class="soc-avatars">
    <div class="soc-av" style="background:#F28500;">K</div>
    <div class="soc-av" style="background:#3B82F6;">T</div>
    <div class="soc-av" style="background:#10B981;">S</div>
    <div class="soc-av" style="background:#8B5CF6;">P</div>
    <div class="soc-av-more">+496</div>
  </div>
  <div class="soc-text">
    <strong>150+ Trendyol ma&#287;azas&#305;</strong> ReOrder ile retention'&#305;n&#305; art&#305;rd&#305;.
    <div style="font-size:.65rem;color:#9ca3af;margin-top:.12rem;">Ortalama 34% daha fazla geri d&#246;nen m&#252;&#351;teri</div>
  </div>
  <div class="soc-rating"><div class="stars">&#9733;&#9733;&#9733;&#9733;&#9733;</div><div class="rating-val">4.9</div></div>
</div>
<!-- PRICING -->
<div class="pricing">
  <div class="sec-tag">Fiyatland&#305;rma</div>
  <div class="sec-title">Ma&#287;azan&#305;za uygun plan</div>
  <div class="sec-sub">Ma&#287;azan&#305;z&#305;n büyüklü&#287;üne göre plan seçin.</div>
  <div class="period-toggle">
    <button class="pt on" onclick="sp('m',this)">Ayl&#305;k</button>
    <button class="pt" onclick="sp('q',this)">3 Ayl&#305;k <span class="sb">&minus;10%</span></button>
    <button class="pt" onclick="sp('y',this)">Y&#305;ll&#305;k <span class="sb">&minus;18%</span></button>
  </div>
  <div class="plans">
    <div class="plan">
      <div class="pn">Starter</div>
      <div class="pp"><span class="pc">&#8378;</span><span class="pa"><span class="pv s" id="sm">349</span><span class="pv" id="sq">875</span><span class="pv" id="sy">2.699</span></span></div>
      <div class="pper" id="sp-pper">/ay</div><div class="pnote" id="sn">ayl&#305;k faturaland&#305;rma</div>
      <div class="psave h" id="ss">&#8212;</div><div class="pd"></div>
      <div class="pf"><div class="pok">&#10003;</div>1 Ma&#287;aza</div>
      <div class="pf"><div class="pok">&#10003;</div>Dashboard &amp; KPI</div>
      <div class="pf"><div class="pok">&#10003;</div>Cohort Analizi</div>
      <div class="pf"><div class="pok">&#10003;</div>D&#246;nem Kar&#351;&#305;la&#351;t&#305;rmas&#305;</div>
      <div class="pf"><div class="pok">&#10003;</div>Anl&#305;k Bildirimler</div>
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">PDF Rapor</span></div>
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">Kampanyalar</span></div>
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">Gelir Tahmini</span></div>
      <button class="pcta cout" onclick="goRegister()">Ba&#351;la</button>
    </div>
    <div class="plan pop">
      <div class="pr">EN POP&#220;LER</div>
      <div class="pn">Pro</div>
      <div class="pp"><span class="pc">&#8378;</span><span class="pa"><span class="pv s" id="pm">699</span><span class="pv" id="pq">1.875</span><span class="pv" id="py">6.900</span></span></div>
      <div class="pper" id="pp-pper">/ay</div><div class="pnote" id="pnn">ayl&#305;k faturaland&#305;rma</div>
      <div class="psave h" id="ps">&#8212;</div><div class="pd"></div>
      <div class="pf"><div class="pok">&#10003;</div>3 Ma&#287;aza</div>
      <div class="pf"><div class="pok">&#10003;</div>Dashboard &amp; KPI + Bildirimler</div>
      <div class="pf"><div class="pok">&#10003;</div>Cohort + RFM + Aksiyon &#214;nerileri</div>
      <div class="pf"><div class="pok">&#10003;</div>&#128302; Gelir Tahmini <span style="font-size:.52rem;background:#F28500;color:#fff;border-radius:4px;padding:.05rem .3rem;vertical-align:middle;">YEN&#304;</span></div>
      <div class="pf"><div class="pok">&#10003;</div>&#128279; Cross-Sell Matrisi <span style="font-size:.52rem;background:#F28500;color:#fff;border-radius:4px;padding:.05rem .3rem;vertical-align:middle;">YEN&#304;</span></div>
      <div class="pf"><div class="pok">&#10003;</div>&#128337; Haftal&#305;k Rapor <span style="font-size:.52rem;background:#F28500;color:#fff;border-radius:4px;padding:.05rem .3rem;vertical-align:middle;">YEN&#304;</span></div>
      <div class="pf"><div class="pok">&#10003;</div>PDF Rapor + Kampanyalar</div>
      <button class="pcta cmain" onclick="goRegister()">&#350;imdi Ba&#351;la &#8594;</button>
    </div>
    <div class="plan">
      <div class="pn">Enterprise</div>
      <div class="pp"><span class="pc">&#8378;</span><span class="pa"><span class="pv s" id="em">1.249</span><span class="pv" id="eq">3.550</span><span class="pv" id="ey">12.000</span></span></div>
      <div class="pper" id="ep-pper">/ay</div><div class="pnote" id="en">ayl&#305;k faturaland&#305;rma</div>
      <div class="psave h" id="es">&#8212;</div><div class="pd"></div>
      <div class="pf"><div class="pok">&#10003;</div>S&#305;n&#305;rs&#305;z Ma&#287;aza</div>
      <div class="pf"><div class="pok">&#10003;</div>T&#252;m Pro &#214;zellikler</div>
      <div class="pf"><div class="pok">&#10003;</div>E-posta Kampanya + Haftal&#305;k Rapor</div>
      <div class="pf"><div class="pok">&#10003;</div>Trendyol API Entegrasyonu</div>
      <div class="pf"><div class="pok">&#10003;</div>&#214;ncelikli Destek + Hesap Y&#246;neticisi</div>
      <button class="pcta cout" onclick="goRegister()">Ba&#351;la</button>
    </div>
  </div>
</div>
<script>
var saves={q:{s:172,p:222,e:197},y:{s:1489,p:1488,e:2988}};
function sp(period,btn){
  document.querySelectorAll('.pt').forEach(function(b){b.classList.remove('on');});
  btn.classList.add('on');
  var ids={s:['sm','sq','sy'],p:['pm','pq','py'],e:['em','eq','ey']};
  var periods=['m','q','y'];
  Object.keys(ids).forEach(function(t){
    ids[t].forEach(function(id,i){
      var el=document.getElementById(id);
      if(el){el.classList.remove('s');if(periods[i]===period)el.classList.add('s');}
    });
  });
  var noteMap={m:'aylık faturalandırma',q:'3 aylık (toplam fiyat)',y:'yıllık (toplam fiyat)'};
  ['sn','pnn','en'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent=noteMap[period];});
  var pperMap={m:'/ay',q:'/3 ay',y:'/yıl'};
  ['sp-pper','pp-pper','ep-pper'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent=pperMap[period];});
  var sv=saves[period];
  [['ss','s'],['ps','p'],['es','e']].forEach(function(pair){
    var el=document.getElementById(pair[0]);if(!el)return;
    if(sv&&sv[pair[1]]){el.textContent='₺'+sv[pair[1]].toLocaleString('tr-TR')+' tasarruf';el.classList.remove('h');}
    else el.classList.add('h');
  });
}
function goRegister(){
    try{ window.parent.sessionStorage.setItem('reorder_go_register','1'); }
    catch(e){}
}
</script>
</body>
</html>"""

        _cmp.html(_left_html, height=920, scrolling=True)

    with col_c:
        st.markdown(
            """
            <div style="text-align:center;margin-bottom:1.6rem;padding-top:.3rem;position:relative;z-index:1;">
                <div style="width:52px;height:52px;border-radius:15px;
                    background:linear-gradient(135deg,#F28500,#C95A10);
                    display:inline-flex;align-items:center;justify-content:center;
                    font-size:1.4rem;box-shadow:0 8px 24px rgba(242,133,0,.45);
                    margin-bottom:.75rem;">&#x1F504;</div>
                <div style="font-size:1.2rem;font-weight:800;color:#fff;letter-spacing:-.01em;">
                    Hesab&#305;na Giri&#351; Yap</div>
                <div style="font-size:.76rem;color:rgba(255,255,255,.32);margin-top:.22rem;">
                    Hesab&#305;n&#305; olu&#351;tur ve hemen kullan</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_giris, tab_kayit = st.tabs(["🔐 Giriş Yap", "✨ Hesap Oluştur"])

        # Pricing buton tıklamasını dinle: sol panel iframe sessionStorage flag koyar,
        # bu component 100ms'de bir okur ve direkt tab'a DOM click atar.
        _cmp.html("""
        <script>
        (function poll(){
            try{
                if(window.parent.sessionStorage.getItem('reorder_go_register')==='1'){
                    window.parent.sessionStorage.removeItem('reorder_go_register');
                    var tabs=window.parent.document.querySelectorAll('[role="tab"]');
                    if(tabs&&tabs.length>1) tabs[1].click();
                }
            }catch(e){}
            setTimeout(poll,100);
        })();
        </script>
        """, height=0)

        with tab_giris:
            if not st.session_state.get("show_forgot"):
                # ── Normal giriş formu ────────────────────────────────────────
                with st.form("login_form"):
                    email = st.text_input("E-posta", placeholder="ornek@magaza.com")
                    password = st.text_input("Şifre", type="password")
                    submitted = st.form_submit_button("Giriş Yap", use_container_width=True)
                if submitted:
                    res = login_user(email, password)
                    if res["success"]:
                        st.session_state.user = res["user"]
                        try:
                            tok = create_session_token(res["user"]["id"])
                            st.query_params["_rt"] = tok
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        st.error(res["error"])
                # Şifremi unuttum linki
                st.markdown(
                    "<div style='text-align:center;margin-top:.3rem;'>",
                    unsafe_allow_html=True,
                )
                if st.button("🔑 Şifremi Unuttum?", key="go_forgot",
                             use_container_width=True):
                    st.session_state.show_forgot = True
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            else:
                # ── Şifremi unuttum formu ─────────────────────────────────────
                st.markdown(
                    "<p style='color:rgba(180,210,230,.7);font-size:.82rem;margin-bottom:.5rem;'>"
                    "E-posta adresinize şifre sıfırlama bağlantısı göndereceğiz.</p>",
                    unsafe_allow_html=True,
                )
                with st.form("forgot_form"):
                    forgot_email = st.text_input("E-posta", placeholder="ornek@magaza.com")
                    sub_forgot = st.form_submit_button("📧 Sıfırlama Bağlantısı Gönder",
                                                       use_container_width=True)
                if sub_forgot:
                    if not forgot_email.strip():
                        st.error("E-posta adresini girin.")
                    else:
                        token = create_reset_token(forgot_email.strip().lower())
                        if token:
                            res = send_reset_email(forgot_email.strip().lower(), token)
                            if res["success"]:
                                st.success("✅ Sıfırlama bağlantısı e-postanıza gönderildi. "
                                           "Gelen kutunuzu kontrol edin (spam klasörünü de).")
                            elif res.get("error") == "no_smtp":
                                # SMTP yapılandırılmamış — geliştirici/admin modu
                                import os as _os
                                app_url = _os.environ.get("APP_URL",
                                    "https://reorder-81nz.onrender.com").rstrip("/")
                                st.warning(
                                    "⚠️ SMTP yapılandırılmamış. "
                                    "Yönetici olarak aşağıdaki bağlantıyı kullanın:"
                                )
                                st.code(f"{app_url}/?reset_token={token}")
                            else:
                                st.error(f"E-posta gönderilemedi: {res['error']}")
                        else:
                            # Güvenlik: email yoksa da aynı mesajı göster
                            st.success("✅ Bu e-posta kayıtlıysa sıfırlama bağlantısı gönderildi.")
                if st.button("← Giriş'e Dön", key="back_to_login"):
                    st.session_state.show_forgot = False
                    st.rerun()

        with tab_kayit:
            with st.form("register_form"):
                store = st.text_input("Mağaza Adı", placeholder="Mağazanızın adı")
                email2 = st.text_input("E-posta", placeholder="ornek@magaza.com")
                pw1 = st.text_input(
                    "Şifre", type="password", help="En az 8 karakter, 1 rakam içermeli"
                )
                pw2 = st.text_input("Şifre (Tekrar)", type="password")
                sub2 = st.form_submit_button("Hesap Oluştur", use_container_width=True)
            if sub2:
                if pw1 != pw2:
                    st.error("Şifreler eşleşmiyor.")
                else:
                    res = register_user(email2, pw1, store)
                    if res["success"]:
                        st.session_state.user = res["user"]
                        st.session_state.new_user = True
                        try:
                            tok = create_session_token(res["user"]["id"])
                            st.query_params["_rt"] = tok
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        st.error(res["error"])


    with col_c:
        st.markdown(
            """
            <div style="margin-top:1.4rem;border-top:1px solid rgba(255,255,255,.07);
                padding-top:1.1rem;text-align:center;">
                <div style="font-size:.72rem;color:rgba(255,255,255,.28);margin-bottom:.6rem;">
                    Sorularınız mı var? Uzmanlarımız yardımcı olsun.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("✉️  Bizimle İletişime Geçin", use_container_width=True, key="open_contact"):
            _contact_dialog()

    # ── Mobil Marketing Bloğu (masaüstünde gizli, mobilde login altında görünür) ──
    st.markdown("""
<div class="ro-mob-marketing" style="display:none;background:#f0f4fa;padding:0 0 4rem;">

  <!-- Özellikler -->
  <div style="padding:1.6rem 1rem 0;">
    <div style="font-size:.6rem;font-weight:700;color:#F28500;text-transform:uppercase;letter-spacing:.12em;margin-bottom:.3rem;">&#10022; Özellikler</div>
    <div style="font-size:1.15rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;margin-bottom:.2rem;">Her şey tek yerden</div>
    <div style="font-size:.79rem;color:#9ca3af;line-height:1.6;margin-bottom:.4rem;">Trendyol mağazanı büyütmek için ihtiyaç duyduğun tüm araçlar.</div>
    <div style="font-size:.72rem;font-weight:800;background:linear-gradient(90deg,#F28500,#ff6b35);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.85rem;">&#10024; 7 yeni özellik eklendi!</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.55rem;">
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">📊</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Anlık Dashboard</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Günlük gelir ve sipariş gerçek zamanlı.</div>
      </div>
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🔥</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Cohort Retention</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Renk kodlu heatmap ile analiz.</div>
      </div>
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">👥</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">RFM & Churn Skoru</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">0-100 risk, 4 müşteri segmenti.</div>
      </div>
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">📧</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">E-posta Kampanya</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Segmente özel şablonlarla gönder.</div>
      </div>
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">📄</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">PDF Rapor</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">3 sayfalık markalı rapor, tek tık.</div>
      </div>
      <div style="background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🏪</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Çoklu Mağaza</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Birden fazla mağaza, tek hesap.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🔮</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Gelir Tahmini</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">90 günlük AI destekli projeksiyon.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🔗</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Cross-Sell Matrisi</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Birlikte satılan ürünler, lift skoru.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">📅</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Dönem Karşılaştırması</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Bu ay vs geçen ay, grafik ile.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🚨</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Anlık Bildirimler</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Gelir düşüşü, ani sipariş uyarısı.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">🎯</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Aksiyon Önerileri</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Segmente özel büyüme adımları.</div>
      </div>
      <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1px solid #F28500;border-radius:12px;padding:.9rem;box-shadow:0 1px 6px rgba(242,133,0,.12);position:relative;overflow:hidden;">
        <div style="position:absolute;top:.4rem;right:.4rem;background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.15rem .35rem;border-radius:4px;letter-spacing:.06em;">YENİ</div>
        <div style="font-size:1.1rem;margin-bottom:.3rem;">📩</div>
        <div style="font-size:.8rem;font-weight:700;color:#0f1a35;margin-bottom:.2rem;">Haftalık Rapor</div>
        <div style="font-size:.71rem;color:#6b7280;line-height:1.5;">Otomatik e-posta özet, her Pazartesi.</div>
      </div>
    </div>
  </div>

  <!-- Sosyal Kanıt -->
  <div style="margin:1.2rem 1rem 0;background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:.85rem 1rem;display:flex;align-items:center;gap:.9rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
    <div style="display:flex;">
      <div style="width:28px;height:28px;border-radius:50%;background:#F28500;border:2px solid #fff;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;color:#fff;">K</div>
      <div style="width:28px;height:28px;border-radius:50%;background:#3B82F6;border:2px solid #fff;margin-left:-7px;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;color:#fff;">T</div>
      <div style="width:28px;height:28px;border-radius:50%;background:#10B981;border:2px solid #fff;margin-left:-7px;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;color:#fff;">S</div>
      <div style="width:28px;height:28px;border-radius:50%;background:#e8edf5;border:2px solid #fff;margin-left:-7px;display:flex;align-items:center;justify-content:center;font-size:.55rem;font-weight:700;color:#6b7280;">+496</div>
    </div>
    <div style="flex:1;">
      <div style="font-size:.75rem;font-weight:700;color:#0f1a35;">150+ Trendyol mağazası</div>
      <div style="font-size:.65rem;color:#9ca3af;margin-top:.1rem;">Ortalama +34% geri dönen müşteri</div>
    </div>
    <div style="font-size:.7rem;font-weight:700;color:#0f1a35;">⭐ 4.9</div>
  </div>

  <!-- Fiyatlandırma -->
  <div style="padding:1.3rem 1rem 0;">
    <div style="font-size:.6rem;font-weight:700;color:#F28500;text-transform:uppercase;letter-spacing:.12em;margin-bottom:.3rem;">&#10022; Fiyatlandırma</div>
    <div style="font-size:1.15rem;font-weight:900;color:#0f1a35;letter-spacing:-.02em;margin-bottom:.2rem;">Mağazanıza uygun plan</div>
    <div style="font-size:.79rem;color:#9ca3af;margin-bottom:1rem;">Büyüklüğünüze göre plan seçin. İstediğiniz zaman değiştirin.</div>
    <!-- Starter -->
    <div style="background:#fff;border:1.5px solid #e8edf5;border-radius:14px;padding:1.1rem;margin-bottom:.6rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
      <div style="font-size:.62rem;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem;">Starter</div>
      <div style="display:flex;align-items:baseline;gap:.1rem;margin-bottom:.15rem;"><span style="font-size:.85rem;font-weight:700;color:#6b7280;">₺</span><span style="font-size:1.7rem;font-weight:900;color:#0f1a35;line-height:1;">349</span><span style="font-size:.62rem;color:#9ca3af;">/ay</span></div>
      <div style="height:1px;background:#f0f2f7;margin:.65rem 0;"></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 1 Mağaza</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Dashboard & KPI</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Cohort Analizi</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Dönem Karşılaştırması</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Anlık Bildirimler</div>
      <div style="font-size:.72rem;color:#c4c9d4;margin-bottom:.28rem;">✗ PDF Rapor</div>
      <div style="font-size:.72rem;color:#c4c9d4;">✗ Gelir Tahmini</div>
    </div>
    <!-- Pro -->
    <div style="background:linear-gradient(135deg,#fff9f0,#fff);border:1.5px solid #F28500;border-radius:14px;padding:1.1rem;margin-bottom:.6rem;box-shadow:0 4px 18px rgba(242,133,0,.14);position:relative;">
      <div style="position:absolute;top:0;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#F28500,#D46000);color:#fff;font-size:.5rem;font-weight:800;letter-spacing:.08em;padding:.2rem 1rem;border-radius:0 0 9px 9px;">EN POPÜLER</div>
      <div style="font-size:.62rem;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem;margin-top:.8rem;">Pro</div>
      <div style="display:flex;align-items:baseline;gap:.1rem;margin-bottom:.15rem;"><span style="font-size:.85rem;font-weight:700;color:#6b7280;">₺</span><span style="font-size:1.7rem;font-weight:900;color:#F28500;line-height:1;">699</span><span style="font-size:.62rem;color:#9ca3af;">/ay</span></div>
      <div style="height:1px;background:#f0f2f7;margin:.65rem 0;"></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 3 Mağaza</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Dashboard & KPI</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Cohort + RFM</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ PDF Rapor</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 🔮 Gelir Tahmini <span style="background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.1rem .3rem;border-radius:3px;margin-left:.2rem;">YENİ</span></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 🔗 Cross-Sell Matrisi <span style="background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.1rem .3rem;border-radius:3px;margin-left:.2rem;">YENİ</span></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 🎯 Aksiyon Önerileri <span style="background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.1rem .3rem;border-radius:3px;margin-left:.2rem;">YENİ</span></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 📧 E-posta Kampanya</div>
      <div style="font-size:.72rem;color:#374151;">✅ 📩 Haftalık Rapor <span style="background:#F28500;color:#fff;font-size:.42rem;font-weight:800;padding:.1rem .3rem;border-radius:3px;margin-left:.2rem;">YENİ</span></div>
    </div>
    <!-- Enterprise -->
    <div style="background:#fff;border:1.5px solid #e8edf5;border-radius:14px;padding:1.1rem;box-shadow:0 1px 4px rgba(0,0,0,.04);">
      <div style="font-size:.62rem;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem;">Enterprise</div>
      <div style="display:flex;align-items:baseline;gap:.1rem;margin-bottom:.15rem;"><span style="font-size:.85rem;font-weight:700;color:#6b7280;">₺</span><span style="font-size:1.7rem;font-weight:900;color:#0f1a35;line-height:1;">1.249</span><span style="font-size:.62rem;color:#9ca3af;">/ay</span></div>
      <div style="height:1px;background:#f0f2f7;margin:.65rem 0;"></div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Sınırsız Mağaza</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Tüm Pro Özellikler</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ 🔌 Trendyol API Entegrasyonu</div>
      <div style="font-size:.72rem;color:#374151;margin-bottom:.28rem;">✅ Öncelikli Destek</div>
      <div style="font-size:.72rem;color:#374151;">✅ Özel Hesap Yöneticisi</div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="ro-login-footer">'
        '<span>ReOrder &copy; 2026</span>'
        '<span class="ro-sep">|</span>'
        '<a href="mailto:support@reorder.app">&#10067; Destek</a>'
        '<span class="ro-sep">|</span>'
        '<a href="#">&#9899; Gizlilik</a>'
        '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plan seçim & ödeme ekranları
# ─────────────────────────────────────────────────────────────────────────────
_ONBOARDING_CSS = """
<style>
[data-testid="stSidebar"]{display:none!important;}
[data-testid="stHeader"]{display:none!important;}
header{display:none!important;}
#MainMenu{display:none!important;}
footer{display:none!important;}
[data-testid="stAppViewContainer"],[data-testid="stApp"],body{
    background:transparent!important;
}
section[data-testid="stMain"]>div:first-child{padding-top:0!important;}
.ob-head{text-align:center;padding:2.8rem 1rem 1.6rem;color:#fff;}
.ob-head h1{font-size:2rem;font-weight:900;margin:0 0 .4rem;}
.ob-head p{color:rgba(255,255,255,.55);font-size:.95rem;margin:0;}
.period-btn button{border-radius:20px!important;font-size:.82rem!important;font-weight:600!important;}
.period-btn [data-testid="stBaseButton-secondary"],
.period-btn button[kind="secondary"]{
    background:rgba(255,255,255,.12)!important;
    color:rgba(255,255,255,.65)!important;
    border:1px solid rgba(255,255,255,.2)!important;
}
.period-btn [data-testid="stBaseButton-secondary"]:hover,
.period-btn button[kind="secondary"]:hover{
    background:rgba(255,255,255,.2)!important;
    color:#fff!important;
}
.plan-card{
    background:rgba(255,255,255,.08);
    border:1.5px solid rgba(255,255,255,.15);
    border-radius:16px;padding:1.6rem 1.4rem 1rem;
    min-height:360px;display:flex;flex-direction:column;
    backdrop-filter:blur(10px);
}
.plan-card-pop{
    background:rgba(242,133,0,.12);
    border:2px solid #F28500;
    box-shadow:0 8px 32px rgba(242,133,0,.25);
}
.plan-badge{
    background:linear-gradient(90deg,#F28500,#D46000);
    color:#fff;font-size:.72rem;font-weight:700;
    letter-spacing:.06em;padding:.28rem .75rem;border-radius:20px;
    display:inline-block;margin-bottom:.9rem;
}
.plan-name{font-size:1.1rem;font-weight:800;color:#fff;margin-bottom:.3rem;}
.plan-price{font-size:2.4rem;font-weight:900;color:#fff;line-height:1;}
.plan-price span{font-size:.95rem;color:rgba(255,255,255,.5);font-weight:400;}
.plan-period-note{font-size:.75rem;color:rgba(255,255,255,.35);margin:.18rem 0 1rem;}
.plan-feat{font-size:.82rem;color:rgba(255,255,255,.75);padding:.22rem 0;
    display:flex;align-items:center;gap:.45rem;}
.plan-feat::before{content:"✓";color:#4ade80;font-weight:700;flex-shrink:0;}
.plan-spacer{flex:1;}
/* ödeme formu */
.pay-wrap{
    max-width:480px;margin:0 auto;padding:2rem 1rem;
}
.pay-summary{
    background:rgba(242,133,0,.12);border:1.5px solid rgba(242,133,0,.35);
    border-radius:12px;padding:1rem 1.4rem;display:flex;
    justify-content:space-between;align-items:center;margin-bottom:1.6rem;
}
.pay-summary-name{color:#fff;font-size:1rem;font-weight:700;}
.pay-summary-price{color:#F28500;font-size:1.3rem;font-weight:900;}
.pay-card-vis{
    background:linear-gradient(135deg,#1a3a4a,#0d2535);
    border:1px solid rgba(255,255,255,.1);border-radius:14px;
    padding:1.6rem;margin-bottom:1.4rem;
    box-shadow:0 8px 32px rgba(0,0,0,.4);
}
.pay-card-chip{
    width:34px;height:26px;background:linear-gradient(135deg,#d4a843,#a07830);
    border-radius:5px;margin-bottom:1rem;
}
.pay-card-number{
    font-size:1.3rem;letter-spacing:.18em;color:#fff;font-weight:600;
    font-family:monospace;margin-bottom:.9rem;
}
.pay-card-footer{display:flex;justify-content:space-between;color:rgba(255,255,255,.6);font-size:.78rem;}
.pay-secure{text-align:center;color:rgba(255,255,255,.35);font-size:.78rem;margin-top:.8rem;}
[data-testid="stTextInput"] label{color:rgba(255,255,255,.65)!important;font-size:.85rem!important;}
[data-testid="stTextInput"] input{
    background:#0d2e40!important;
    border:1.5px solid rgba(255,255,255,.2)!important;
    color:#fff!important;border-radius:10px!important;
}
[data-testid="stTextInput"] input::placeholder{color:rgba(255,255,255,.35)!important;}
[data-testid="stTextInput"] input:focus{
    border-color:#F28500!important;
    box-shadow:0 0 0 2px rgba(242,133,0,.2)!important;
}
.stForm [data-testid="stFormSubmitButton"] button{
    background:linear-gradient(135deg,#F28500,#D46000)!important;
    color:#fff!important;font-weight:700!important;
    border-radius:12px!important;font-size:1rem!important;
}
</style>
"""


def show_plan_selection() -> None:
    """Yeni kayıt sonrası plan seçim ekranı."""
    st.markdown(_ONBOARDING_BG + _ONBOARDING_CSS, unsafe_allow_html=True)

    user = st.session_state.user
    store_name = user.get("store_name", "") if user else ""
    st.markdown(
        f'<div class="ob-head"><h1>Hoş Geldin{", " + store_name if store_name else ""}! 🎉</h1>'
        '<p>Mağazanız için en uygun planı seçin. İstediğiniz zaman değiştirebilirsiniz.</p></div>',
        unsafe_allow_html=True,
    )

    period = st.session_state.plan_period
    period_labels = {"m": "Aylık", "q": "3 Aylık  −10%", "y": "Yıllık  −18%"}
    period_note = {"m": "aylık faturalandırma", "q": "3 aylık toplam fiyat", "y": "yıllık toplam fiyat"}

    _, tc1, tc2, tc3, _ = st.columns([2, 1.5, 1.5, 1.5, 2])
    with tc1:
        st.markdown('<div class="period-btn">', unsafe_allow_html=True)
        if st.button("Aylık", use_container_width=True,
                     type="primary" if period == "m" else "secondary", key="pb_m"):
            st.session_state.plan_period = "m"; st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with tc2:
        st.markdown('<div class="period-btn">', unsafe_allow_html=True)
        if st.button("3 Aylık −10%", use_container_width=True,
                     type="primary" if period == "q" else "secondary", key="pb_q"):
            st.session_state.plan_period = "q"; st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with tc3:
        st.markdown('<div class="period-btn">', unsafe_allow_html=True)
        if st.button("Yıllık −18%", use_container_width=True,
                     type="primary" if period == "y" else "secondary", key="pb_y"):
            st.session_state.plan_period = "y"; st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)

    _, c1, c2, c3, _ = st.columns([0.4, 3, 3.2, 3, 0.4])
    plans = [("Starter", c1, False), ("Pro", c2, True), ("Enterprise", c3, False)]
    for plan_name, col, popular in plans:
        price, unit = _PLAN_PRICES[period][plan_name]
        feats = _PLAN_FEATURES[plan_name]
        feats_html = "".join(f'<div class="plan-feat">{f}</div>' for f in feats)
        badge = '<div class="plan-badge">EN POPÜLER</div>' if popular else ""
        card_cls = "plan-card plan-card-pop" if popular else "plan-card"
        with col:
            st.markdown(
                f'<div class="{card_cls}">'
                f'{badge}'
                f'<div class="plan-name">{plan_name}</div>'
                f'<div class="plan-price">₺{price:,}<span> {unit}</span></div>'
                f'<div class="plan-period-note">{period_note[period]}</div>'
                f'{feats_html}'
                f'<div class="plan-spacer"></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            btn_label = f"✨ {plan_name} Planını Seç" if popular else f"{plan_name} Planını Seç"
            if st.button(btn_label, use_container_width=True,
                         type="primary" if popular else "secondary",
                         key=f"sel_{plan_name}"):
                st.session_state.selected_plan = {
                    "name": plan_name,
                    "price": price,
                    "unit": unit,
                    "period": period,
                }
                st.rerun()

    st.markdown(
        '<div style="text-align:center;margin-top:2rem;color:rgba(255,255,255,.3);font-size:.78rem;">'
        '🔒 Güvenli ödeme · SSL şifreli · İstediğiniz zaman iptal</div>',
        unsafe_allow_html=True,
    )


def show_payment() -> None:
    """Ödeme formu ekranı."""
    st.markdown(_ONBOARDING_BG + _ONBOARDING_CSS, unsafe_allow_html=True)
    plan = st.session_state.selected_plan or {}
    plan_name = plan.get("name", "")
    price = plan.get("price", 0)
    unit = plan.get("unit", "/ay")

    st.markdown(
        '<div class="ob-head"><h1>💳 Ödeme Bilgileri</h1>'
        '<p>Kartınızı güvenli biçimde kaydedin ve planınızı aktifleştirin.</p></div>',
        unsafe_allow_html=True,
    )

    _, col_main, _ = st.columns([1, 3, 1])
    with col_main:
        st.markdown(
            f'<div class="pay-summary">'
            f'<div class="pay-summary-name">📦 {plan_name} Planı</div>'
            f'<div class="pay-summary-price">₺{price:,}<span style="font-size:.85rem;color:rgba(255,255,255,.5)">{unit}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="pay-card-vis">'
            '<div class="pay-card-chip"></div>'
            '<div class="pay-card-number">•••• •••• •••• ••••</div>'
            '<div class="pay-card-footer"><span>KART SAHİBİ</span><span>AA/YY</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )

        with st.form("payment_form"):
            cardholder = st.text_input("Kart Sahibinin Adı", placeholder="Ad Soyad")
            card_no = st.text_input("Kart Numarası", placeholder="0000 0000 0000 0000", max_chars=19)
            col_exp, col_cvv = st.columns(2)
            with col_exp:
                expiry = st.text_input("Son Kullanma Tarihi", placeholder="AA/YY", max_chars=5)
            with col_cvv:
                cvv = st.text_input("CVV", placeholder="•••", max_chars=4, type="password")

            submitted = st.form_submit_button(
                f"🔒  ₺{price:,}{unit} Öde ve Başla",
                use_container_width=True,
            )

        if submitted:
            if not all([cardholder.strip(), card_no.strip(), expiry.strip(), cvv.strip()]):
                st.error("Lütfen tüm kart bilgilerini doldurun.")
            else:
                period = st.session_state.get("plan_period", "m")
                user_id = st.session_state.user["id"]
                save_user_plan(user_id, plan_name, period)
                st.session_state.user["plan"] = plan_name
                st.session_state.user["plan_period"] = period
                st.session_state.new_user = False
                st.session_state.selected_plan = None
                st.success(f"✅ {plan_name} planınız aktifleştirildi! Yönlendiriliyorsunuz…")
                import time; time.sleep(1.2)
                st.rerun()

        st.markdown(
            '<div style="text-align:center;margin-top:.6rem">'
            '<button style="background:none;border:none;color:rgba(255,255,255,.4);'
            'cursor:pointer;font-size:.82rem;text-decoration:underline" '
            'onclick="void(0)">← Plan Değiştir</button></div>',
            unsafe_allow_html=True,
        )
        if st.button("← Plan Değiştir", key="back_to_plans"):
            st.session_state.selected_plan = None
            st.rerun()

        st.markdown(
            '<div class="pay-secure">🔒 256-bit SSL şifreli · Kart bilgileriniz güvende</div>',
            unsafe_allow_html=True,
        )


def show_sidebar() -> None:
    user = st.session_state.user
    current_page = st.session_state.get("page", "dashboard")
    stores = st.session_state.get("stores", [])
    active_store_id = st.session_state.get("active_store_id")

    with st.sidebar:
        # ReOrder başlığı — tıklanınca Genel Bakış açılır
        if st.button("🔄 ReOrder", key="sidebar_logo_btn", use_container_width=True):
            _go("dashboard")
        _u_plan = user.get("plan", "Starter")
        _badge_col = _PLAN_BADGE_COLOR.get(_u_plan, "#6B7280")
        st.markdown(
            f"""
            <div style="padding:.1rem .2rem 1.1rem; border-bottom:1px solid rgba(255,255,255,.1); text-align:center;">
                <div style="font-size:.72rem; opacity:.5; margin-top:.2rem;">{user['email']}</div>
                <div style="margin-top:.5rem;">
                    <span style="
                        display:inline-block;
                        background:{_badge_col}22;
                        border:1px solid {_badge_col}88;
                        color:{_badge_col};
                        border-radius:20px;
                        font-size:.68rem;
                        font-weight:700;
                        padding:.18rem .65rem;
                        letter-spacing:.05em;
                    ">{_u_plan.upper()}</span>
                </div>
                <div style="
                    margin-top:.55rem;
                    font-size:.8rem;
                    font-style:italic;
                    font-weight:700;
                    letter-spacing:.03em;
                    background:linear-gradient(90deg,#F28500,#ffb347);
                    -webkit-background-clip:text;
                    -webkit-text-fill-color:transparent;
                    background-clip:text;
                    line-height:1.35;
                ">Kusursuz Deneyim, Geri Dönen Müşteriler.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Mağaza Seçici ────────────────────────────────────────────────────
        st.markdown("&nbsp;")
        st.markdown(
            '<div style="font-size:.7rem;font-weight:700;color:rgba(255,255,255,.4);'
            'letter-spacing:.08em;text-transform:uppercase;margin-bottom:.35rem;">🏪 Aktif Mağaza</div>',
            unsafe_allow_html=True,
        )

        if stores:
            store_names = [s["store_name"] for s in stores]
            store_ids   = [s["id"] for s in stores]
            try:
                current_idx = store_ids.index(active_store_id) if active_store_id in store_ids else 0
            except ValueError:
                current_idx = 0

            selected_idx = st.selectbox(
                "Mağaza",
                options=range(len(stores)),
                format_func=lambda i: store_names[i],
                index=current_idx,
                label_visibility="collapsed",
                key="store_selector",
            )
            if store_ids[selected_idx] != active_store_id:
                st.session_state.active_store_id = store_ids[selected_idx]
                st.rerun()

            active_store = stores[current_idx]
            # Trendyol API bilgileri var mı? — session_state'de cache'le, her render'da DB'ye gitme
            _cred_key = f"_ty_creds_{user['id']}_{active_store['id']}"
            if _cred_key not in st.session_state:
                try:
                    from src.trendyol_api import load_credentials as _lc
                    st.session_state[_cred_key] = _lc(user["id"], active_store["id"])
                except Exception:
                    st.session_state[_cred_key] = None
            creds = st.session_state[_cred_key]

            if creds:
                last_sync = creds.get("last_sync_at")
                sync_label = "Henüz senkronize edilmedi"
                if last_sync:
                    try:
                        import datetime as _dt
                        if isinstance(last_sync, str):
                            _ls = _dt.datetime.fromisoformat(last_sync.replace("Z", ""))
                        else:
                            _ls = last_sync
                        mins = int((_dt.datetime.now() - _ls).total_seconds() / 60)
                        sync_label = f"{mins} dk önce senkronize edildi" if mins < 60 else f"{mins//60} sa önce"
                    except Exception:
                        sync_label = str(last_sync)[:16]
                st.markdown(
                    f'<div style="font-size:.71rem;color:rgba(255,255,255,.38);margin:.2rem 0 .4rem;">'
                    f'⏱ {sync_label}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("🔄 Son 7 Günü Senkronize Et", use_container_width=True, key="quick_sync"):
                    import datetime as _dt
                    today = _dt.date.today()
                    start = (today - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
                    end   = today.strftime("%Y-%m-%d")
                    with st.spinner("Senkronize ediliyor…"):
                        from src.trendyol_api import sync_orders as _so
                        res = _so(user["id"], start, end, active_store["id"])
                    if res["success"]:
                        st.success(f"✅ {res['inserted']} yeni sipariş eklendi.")
                        # Mağaza listesini, credentials cache'ini ve analytics cache'ini yenile
                        st.session_state.stores = get_stores(user["id"])
                        st.session_state.pop(_cred_key, None)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(res["error"])

        # ── Yeni mağaza ekle ─────────────────────────────────────────────────
        with st.expander("➕ Mağaza Ekle / Yönet"):
            _max_stores = _plan_limits()["max_stores"]
            _store_count = len(stores) if stores else 0
            _at_limit = _max_stores is not None and _store_count >= _max_stores
            if _at_limit:
                _upgrade_to = _PLAN_UPGRADE.get(user.get("plan", "Starter"))
                st.warning(
                    f"Planınız en fazla **{_max_stores} mağaza** destekler. "
                    + (f"Daha fazlası için **{_upgrade_to}** planına geçin — **Ayarlar → Plan Yönetimi**." if _upgrade_to else "")
                )
            else:
                new_store_name = st.text_input("Yeni Mağaza Adı", placeholder="Mağaza adı", key="new_store_input")
                if st.button("Ekle", key="add_store_btn", use_container_width=True):
                    if new_store_name.strip():
                        new_id = create_store(user["id"], new_store_name.strip())
                        st.session_state.stores = get_stores(user["id"])
                        st.session_state.active_store_id = new_id
                        st.success(f"'{new_store_name}' eklendi!")
                        st.rerun()
                    else:
                        st.error("Mağaza adı boş olamaz.")

            if stores and len(stores) > 1:
                st.markdown("---")
                st.caption("Mağaza Sil (Veriler de silinir!)")
                del_store = st.selectbox(
                    "Silinecek mağaza",
                    options=[s["id"] for s in stores if s["id"] != active_store_id],
                    format_func=lambda sid: next((s["store_name"] for s in stores if s["id"] == sid), str(sid)),
                    key="del_store_select",
                )
                if st.button("🗑️ Sil", key="del_store_btn", use_container_width=True):
                    delete_store(del_store, user["id"])
                    st.session_state.stores = get_stores(user["id"])
                    if st.session_state.stores:
                        st.session_state.active_store_id = st.session_state.stores[0]["id"]
                    st.rerun()

        st.markdown("&nbsp;")

        pages = [
            ("📊", "Genel Bakış", "dashboard"),
            ("📁", "Veri Yükle", "upload"),
            ("📈", "Analitik", "analytics"),
            ("👥", "Müşteri Segmentleri", "segments"),
            ("📧", "Kampanyalar", "campaigns"),
            ("⚙️", "Ayarlar", "settings"),
        ]
        for icon, label, key in pages:
            if current_page == key:
                # Aktif sayfa — tıklanamaz vurgulu div
                st.markdown(
                    f"""<div style="
                        background: linear-gradient(135deg,rgba(242,122,26,.28),rgba(242,122,26,.12));
                        border: 1px solid rgba(242,122,26,.5);
                        border-left: 3px solid #F27A1A;
                        border-radius: 8px;
                        padding: .72rem 1rem;
                        margin-bottom: .25rem;
                        color: #fff;
                        font-weight: 700;
                        font-size: .88rem;
                        letter-spacing: .01em;
                        cursor: default;
                    ">{icon}&nbsp;&nbsp;{label}</div>""",
                    unsafe_allow_html=True,
                )
            else:
                if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True):
                    _go(key)

        st.markdown("---")
        if st.button("🚪  Çıkış Yap", use_container_width=True, key="logout_btn"):
            # Oturum token'ını sil ve URL parametresini temizle
            tok = st.query_params.get("_rt")
            if tok:
                try:
                    delete_session_token(tok)
                except Exception:
                    pass
            st.query_params.clear()
            st.session_state.user = None
            st.session_state.page = "dashboard"
            st.session_state.stores = []
            st.session_state.active_store_id = None
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Yönlendirici
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    # Şifre sıfırlama akışı öncelikli
    if st.session_state.get("reset_token"):
        show_reset_password()
        return

    if st.session_state.user is None:
        show_auth()
        return

    if st.session_state.get("new_user"):
        if st.session_state.get("selected_plan"):
            show_payment()
        else:
            show_plan_selection()
        return

    show_sidebar()

    page = st.session_state.page
    if page == "dashboard":
        from pages.dashboard import run as _run; _run()
    elif page == "upload":
        from pages.upload import run as _run; _run()
    elif page == "analytics":
        from pages.analytics import run as _run; _run()
    elif page == "segments":
        from pages.segments import run as _run; _run()
    elif page == "campaigns":
        from pages.campaigns import run as _run; _run()
    elif page == "settings":
        from pages.settings import run as _run; _run()
    else:
        from pages.dashboard import run as _run; _run()


main()
