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

from src.database import init_db as _init_db, get_stores, create_store, rename_store, delete_store, save_goals, load_goals, link_null_orders
from src.auth import (
    login_user, register_user, update_store_name, change_password,
    create_session_token, verify_session_token, delete_session_token,
)
from src.parser import parse_trendyol_file, import_to_db, generate_sample_orders
from src.report import generate_report
from src.trendyol_api import (
    save_credentials, load_credentials, sync_orders,
    TrendyolClient, TrendyolAPIError,
)
from src.email_service import (
    save_smtp_settings, load_smtp_settings,
    send_test_email, send_campaign_report,
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
    # Yeni özellikler
    get_customer_detail,
    get_current_month_metrics,
    get_product_analysis,
)

# ─────────────────────────────────────────────────────────────────────────────
# Başlatma — cache_resource ile yalnızca bir kez çalışır (rerun'larda atlanır)
# _SCHEMA_VER değiştiğinde cache kırılır ve init_db() yeniden çalışır.
# Yeni tablo/sütun eklendiğinde bu sabiti artır!
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA_VER = "v6"  # orders unique constraint store_id eklendi


@st.cache_resource
def _init_db_once(_ver: str = _SCHEMA_VER):
    _init_db()


_init_db_once(_SCHEMA_VER)

# Carousel PNG'lerini yükleme anında WebP'ye çevirip base64 olarak göm.
# Tam boy (1280px) WebP q90 ~267KB (eski ham PNG 4.65MB) — görseller panelde küçülmesin diye
# çözünürlük düşürülmez, sadece WebP sıkıştırması uygulanır.
_CAROUSEL_MAX_W = 1280  # tam boy korunur (kaynak zaten 1280) — downscale yok
_CAROUSEL_QUALITY = 90

@st.cache_data
def _load_carousel_images():
    import base64
    import os
    import io
    slides = {}
    asset_dir = os.path.join(os.path.dirname(__file__), 'assets')
    files = [('slide_dashboard.png', 's0'), ('slide_cohort.png', 's1'),
             ('slide_segments.png', 's2'), ('slide_pdf.png', 's3')]
    try:
        from PIL import Image
    except ImportError:
        Image = None
    for fname, key in files:
        fpath = os.path.join(asset_dir, fname)
        if not os.path.exists(fpath):
            continue
        if Image is not None:
            try:
                im = Image.open(fpath).convert('RGB')
                if im.width > _CAROUSEL_MAX_W:
                    ratio = _CAROUSEL_MAX_W / im.width
                    im = im.resize((_CAROUSEL_MAX_W, round(im.height * ratio)),
                                   Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format='WEBP', quality=_CAROUSEL_QUALITY, method=6)
                slides[key] = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
                continue
            except Exception:
                pass  # PIL/WebP başarısız olursa ham PNG'ye düş
        with open(fpath, 'rb') as f:
            slides[key] = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
    return slides

_CAROUSEL_IMGS = _load_carousel_images()

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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_tl(val: float) -> str:
    return f"₺{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _kpi(label: str, value: str, sub: str = "", icon: str = "") -> None:
    icon_html = (
        f'<span style="position:absolute;top:.75rem;right:.8rem;width:34px;height:34px;'
        f'border-radius:9px;background:rgba(242,122,26,.1);display:inline-flex;'
        f'align-items:center;justify-content:center;font-size:1.1rem;">{icon}</span>'
    ) if icon else ""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="kpi-card" style="position:relative;">'
        f'{icon_html}'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}'
        f'</div>',
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
.feat{background:#fff;border:1px solid #e8edf5;border-radius:12px;padding:1rem 1.1rem;box-shadow:0 1px 4px rgba(0,0,0,.04);transition:all .22s;cursor:default;}
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
  <div class="sec-sub">Trendyol ma&#287;azan&#305; b&#252;y&#252;tmek i&#231;in ihtiya&#231; duydu&#287;un t&#252;m ara&#231;lar.</div>
  <div class="feat-grid">
    <div class="feat">
      <div class="feat-top"><div class="fi fi-or">&#128202;</div><div class="ft">Anl&#305;k Dashboard</div></div>
      <div class="fd">G&#252;nl&#252;k gelir, sipari&#351; ve aktif m&#252;&#351;teriyi ger&#231;ek zamanl&#305; izle. Otomatik API senkronizasyonu.</div>
      <div class="ftags"><span class="tag to">Ger&#231;ek Zamanl&#305;</span><span class="tag tb">Grafik</span><span class="tag to">API</span></div>
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
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">PDF Rapor</span></div>
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">Kampanyalar</span></div>
      <button class="pcta cout" onclick="goRegister()">Ba&#351;la</button>
    </div>
    <div class="plan pop">
      <div class="pr">EN POP&#220;LER</div>
      <div class="pn">Pro</div>
      <div class="pp"><span class="pc">&#8378;</span><span class="pa"><span class="pv s" id="pm">699</span><span class="pv" id="pq">1.875</span><span class="pv" id="py">6.900</span></span></div>
      <div class="pper" id="pp-pper">/ay</div><div class="pnote" id="pnn">ayl&#305;k faturaland&#305;rma</div>
      <div class="psave h" id="ps">&#8212;</div><div class="pd"></div>
      <div class="pf"><div class="pok">&#10003;</div>3 Ma&#287;aza</div>
      <div class="pf"><div class="pok">&#10003;</div>Dashboard &amp; KPI</div>
      <div class="pf"><div class="pok">&#10003;</div>Cohort + RFM</div>
      <div class="pf"><div class="pok">&#10003;</div>PDF Rapor</div>
      <div class="pf"><div class="pno">&#10005;</div><span class="dim">Kampanyalar</span></div>
      <button class="pcta cmain" onclick="goRegister()">&#350;imdi Ba&#351;la &#8594;</button>
    </div>
    <div class="plan">
      <div class="pn">Enterprise</div>
      <div class="pp"><span class="pc">&#8378;</span><span class="pa"><span class="pv s" id="em">1.249</span><span class="pv" id="eq">3.550</span><span class="pv" id="ey">12.000</span></span></div>
      <div class="pper" id="ep-pper">/ay</div><div class="pnote" id="en">ayl&#305;k faturaland&#305;rma</div>
      <div class="psave h" id="es">&#8212;</div><div class="pd"></div>
      <div class="pf"><div class="pok">&#10003;</div>S&#305;n&#305;rs&#305;z Ma&#287;aza</div>
      <div class="pf"><div class="pok">&#10003;</div>T&#252;m Pro &#214;zellikler</div>
      <div class="pf"><div class="pok">&#10003;</div>E-posta Kampanya</div>
      <div class="pf"><div class="pok">&#10003;</div>&#214;ncelikli Destek</div>
      <div class="pf"><div class="pok">&#10003;</div>API Eri&#351;imi</div>
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
    var url=window.parent.location.href.split('?')[0];
    window.parent.location.href=url+'?action=register';
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

        if st.query_params.get("action") == "register":
            st.markdown("""
            <script>
            (function(){
                function tryClick(n){
                    var tabs=window.parent.document.querySelectorAll('[role="tab"]');
                    if(tabs&&tabs.length>1){tabs[1].click();}
                    else if(n>0){setTimeout(function(){tryClick(n-1);},200);}
                }
                setTimeout(function(){tryClick(15);},250);
            })();
            </script>
            """, unsafe_allow_html=True)

        with tab_giris:
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


def show_sidebar() -> None:
    user = st.session_state.user
    current_page = st.session_state.get("page", "dashboard")
    stores = st.session_state.get("stores", [])
    active_store_id = st.session_state.get("active_store_id")

    with st.sidebar:
        # ReOrder başlığı — tıklanınca Genel Bakış açılır
        if st.button("🔄 ReOrder", key="sidebar_logo_btn", use_container_width=True):
            _go("dashboard")
        st.markdown(
            f"""
            <div style="padding:.1rem .2rem 1.1rem; border-bottom:1px solid rgba(255,255,255,.1); text-align:center;">
                <div style="font-size:.72rem; opacity:.5; margin-top:.2rem;">{user['email']}</div>
                <div style="
                    margin-top:.65rem;
                    font-size:.8rem;
                    font-style:italic;
                    font-weight:700;
                    letter-spacing:.03em;
                    background:linear-gradient(90deg,#F28500,#ffb347);
                    -webkit-background-clip:text;
                    -webkit-text-fill-color:transparent;
                    background-clip:text;
                    line-height:1.35;
                ">Seamless Experience, Return Customers.<br>
                <span style="font-size:.75rem;font-weight:600;">Kusursuz Deneyim, Geri Dönen Müşteriler.</span></div>
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
            # Trendyol API bilgileri var mı?
            creds = None
            try:
                from src.trendyol_api import load_credentials as _lc
                creds = _lc(user["id"], active_store["id"])
            except Exception:
                pass

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
                        # Mağaza listesini ve cache'i yenile
                        st.session_state.stores = get_stores(user["id"])
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(res["error"])

        # ── Yeni mağaza ekle ─────────────────────────────────────────────────
        with st.expander("➕ Mağaza Ekle / Yönet"):
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
# Sayfa: Genel Bakış
# ─────────────────────────────────────────────────────────────────────────────
def show_dashboard() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    stores = st.session_state.get("stores", [])
    store_name = next((s["store_name"] for s in stores if s["id"] == store_id), user["store_name"])
    _header("📊", "Genel Bakış", f"{store_name} — Müşteri Metrikleri")

    m = get_summary_metrics(user["id"], store_id)

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
        _kpi("Toplam Sipariş", f"{m['total_orders']:,}", icon="🛒")
    with c2:
        _kpi("Benzersiz Müşteri", f"{m['unique_customers']:,}", icon="👤")
    with c3:
        _kpi("Toplam Gelir", _fmt_tl(m["total_revenue"]), icon="💰")
    with c4:
        _kpi("Ort. Sipariş Değeri", _fmt_tl(m["avg_order_value"]), icon="📊")

    st.markdown("&nbsp;")

    # ── KPI Satırı 2 ──
    c1, c2, c3, _ = st.columns(4)
    with c1:
        _kpi(
            "Tekrar Eden Müşteriler",
            f"%{m['repeat_rate']}",
            f"{m['repeat_customers']:,} müşteri geri döndü",
            icon="🔄",
        )
    with c2:
        _kpi("Ortalama LTV", _fmt_tl(m["avg_ltv"]), "Müşteri başı ömür boyu değer", icon="💎")
    with c3:
        _kpi("En Yüksek LTV", _fmt_tl(m["top_customer_revenue"]), "Tek müşteri rekoru", icon="🏆")

    st.markdown("&nbsp;")

    # ── Grafikler ──
    trend = get_monthly_trend(user["id"], store_id)
    nvr = get_new_vs_returning(user["id"], store_id)

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

    # ══════════════════════════════════════════════════════════════════════════
    # Mini Dashboard — Trendyol Veri Analitiği Grafikleri
    # ══════════════════════════════════════════════════════════════════════════

    # Özel CSS — st.metric kartlarını mevcut tasarımla uyumlu hale getirir
    st.markdown("""
    <style>
    /* ── Mini Dashboard bölüm ayracı ── */
    .mini-dash-divider {
        border: none;
        border-top: 1px solid rgba(242,122,26,.18);
        margin: 1.6rem 0 1rem 0;
    }
    /* ── st.metric kart alanı ── */
    [data-testid="stMetric"] {
        background: #ffffff;
        border-radius: 12px;
        padding: .9rem 1.1rem !important;
        border-left: 4px solid #F27A1A;
        box-shadow: 0 1px 6px rgba(0,0,0,.06);
    }
    [data-testid="stMetricLabel"] p {
        font-size: .76rem !important;
        font-weight: 700 !important;
        color: #6B7280 !important;
        text-transform: uppercase;
        letter-spacing: .05em;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 800 !important;
        color: #1A1A2E !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: .78rem !important;
    }
    </style>
    <hr class="mini-dash-divider">
    """, unsafe_allow_html=True)

    _section("📊 Sipariş Analitiği")

    # ── 1. KPI Kartları ──────────────────────────────────────────────────────
    kpis = get_order_status_kpis(user["id"], store_id)

    k1, k2, k3 = st.columns(3)
    with k1:
        # st.metric büyük değerleri keser; kısa format kullan
        rev_k = kpis["total_revenue"] / 1000
        rev_str = f"₺{rev_k:,.1f}K" if kpis["total_revenue"] >= 10_000 else _fmt_tl(kpis["total_revenue"])
        st.metric(
            label="💰 Toplam Ciro",
            value=rev_str,
            delta=f"{m['total_orders']:,} toplam sipariş",
            delta_color="off",
        )
    with k2:
        st.metric(
            label="⏳ Aktif Siparişler",
            value=f"{kpis['pending']:,}",
            delta="Bekleyen (Pending)",
            delta_color="normal" if kpis["pending"] > 0 else "off",
        )
    with k3:
        completed_pct = (
            round(kpis["completed"] / m["total_orders"] * 100, 1)
            if m["total_orders"] > 0 else 0.0
        )
        st.metric(
            label="✅ Tamamlanan Siparişler",
            value=f"{kpis['completed']:,}",
            delta=f"%{completed_pct} tamamlanma oranı",
            delta_color="normal" if kpis["completed"] > 0 else "off",
        )

    st.markdown("&nbsp;")

    # ── 2 & 3. Grafik Satırı ─────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2, gap="medium")

    # ── En Çok Satan Ürünler (Bar Chart) ─────────────────────────────────────
    with chart_col1:
        _section("🏆 En Çok Satan Ürünler")
        top_prods = get_top_products(user["id"], n=8, store_id=store_id)

        if top_prods.empty:
            st.markdown(
                '<div class="info-box" style="font-size:.84rem;">'
                '📦 Ürün verisi bulunamadı. Siparişlerde <b>ürün adı</b> sütunu dolu değil veya henüz veri yüklenmedi.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # Uzun isimleri kısalt (grafik genişliğine sığsın diye)
            top_prods["product_label"] = top_prods["product_name"].apply(
                lambda x: x[:28] + "…" if len(str(x)) > 28 else x
            )
            fig_prod = go.Figure(
                go.Bar(
                    x=top_prods["total_qty"],
                    y=top_prods["product_label"],
                    orientation="h",
                    marker=dict(
                        color=top_prods["total_qty"],
                        colorscale=[[0, "#fdba74"], [0.5, "#F27A1A"], [1, "#c2410c"]],
                        showscale=False,
                    ),
                    text=top_prods["total_qty"].apply(lambda v: f"{int(v):,} adet"),
                    textposition="outside",
                    textfont=dict(size=11, color="#374151"),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Miktar: %{x:,.0f} adet<br>"
                        "Gelir: ₺%{customdata:,.2f}<extra></extra>"
                    ),
                    customdata=top_prods["total_revenue"],
                )
            )
            fig_prod.update_layout(
                height=max(260, len(top_prods) * 36 + 40),
                margin=dict(l=0, r=60, t=8, b=0),
                xaxis=dict(
                    title="Toplam Satış Adedi",
                    showgrid=True,
                    gridcolor="#F3F4F6",
                    zeroline=False,
                ),
                yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                template="plotly_white",
                plot_bgcolor="#FAFAFA",
                paper_bgcolor="white",
            )
            st.plotly_chart(fig_prod, use_container_width=True)

    # ── Günlük Ciro Trendi (Line Chart) ──────────────────────────────────────
    with chart_col2:
        _section("📅 Günlük Ciro Trendi")
        daily_rev = get_daily_revenue(user["id"], days=30, store_id=store_id)

        if daily_rev.empty:
            st.markdown(
                '<div class="info-box" style="font-size:.84rem;">'
                '📅 Günlük ciro verisi oluşturulamadı.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # Veri aralığı etiketi
            date_range_label = (
                f"{daily_rev['date_str'].iloc[0]} → {daily_rev['date_str'].iloc[-1]}"
                if len(daily_rev) > 1 else daily_rev["date_str"].iloc[0]
            )
            st.markdown(
                f'<div style="font-size:.76rem; color:#9CA3AF; margin:-6px 0 6px 0;">'
                f'📆 {date_range_label}</div>',
                unsafe_allow_html=True,
            )

            fig_daily = go.Figure()

            # Alan dolgusu
            fig_daily.add_trace(go.Scatter(
                x=daily_rev["date_str"],
                y=daily_rev["revenue"],
                mode="lines+markers",
                name="Günlük Ciro",
                line=dict(color="#F27A1A", width=2.5, shape="spline"),
                marker=dict(size=5, color="#F27A1A", line=dict(width=1.5, color="white")),
                fill="tozeroy",
                fillcolor="rgba(242,122,26,.10)",
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Ciro: ₺%{y:,.2f}<br>"
                    "Sipariş: %{customdata}<extra></extra>"
                ),
                customdata=daily_rev["orders"],
            ))

            # 7 günlük hareketli ortalama (en az 3 nokta varsa)
            if len(daily_rev) >= 3:
                roll = daily_rev["revenue"].rolling(window=min(7, len(daily_rev)), min_periods=1).mean()
                fig_daily.add_trace(go.Scatter(
                    x=daily_rev["date_str"],
                    y=roll,
                    mode="lines",
                    name="7G Ort.",
                    line=dict(color="#3B82F6", width=1.5, dash="dot"),
                    hoverinfo="skip",
                ))

            fig_daily.update_layout(
                height=max(260, len(daily_rev) * 8 + 140),
                margin=dict(l=0, r=0, t=8, b=0),
                xaxis=dict(
                    title="",
                    showgrid=False,
                    tickangle=-35,
                    tickfont=dict(size=10),
                ),
                yaxis=dict(
                    title="Ciro (₺)",
                    showgrid=True,
                    gridcolor="#F3F4F6",
                    zeroline=False,
                    tickprefix="₺",
                    tickformat=",.0f",
                ),
                template="plotly_white",
                plot_bgcolor="#FAFAFA",
                paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
                hovermode="x unified",
            )
            st.plotly_chart(fig_daily, use_container_width=True)

    # ── Bölüm ayracı ─────────────────────────────────────────────────────────
    st.markdown('<hr class="mini-dash-divider">', unsafe_allow_html=True)

    # ── Hedef / KPI Takibi ───────────────────────────────────────────────────
    goals = load_goals(user["id"], store_id)
    if goals:
        _section("🎯 Bu Ay — Hedef Takibi")
        cur_m = get_current_month_metrics(user["id"], store_id)
        goal_cols = st.columns(len(goals))
        goal_meta = {
            "gelir":      ("💰 Aylık Gelir",     cur_m["revenue"],        "₺", "#F27A1A"),
            "musterí":    ("👤 Yeni Müşteri",    cur_m["new_customers"],  "",  "#3B82F6"),
            "retention":  ("🔄 Retention Oranı", cur_m["retention_rate"], "%", "#10B981"),
        }
        for i, (metric, target) in enumerate(goals.items()):
            meta = goal_meta.get(metric, (metric, 0, "", "#6B7280"))
            label, current, unit, color = meta
            pct = min(round(current / target * 100) if target else 0, 100)
            cur_fmt = f"{current:,.1f}" if isinstance(current, float) else str(current)
            tgt_fmt = f"{target:,.0f}"
            with goal_cols[i]:
                st.markdown(
                    f"""<div style="background:white;border-radius:14px;padding:1rem 1.2rem;
                        border-left:4px solid {color};box-shadow:0 2px 8px rgba(0,0,0,.07);">
                        <div style="font-size:.72rem;font-weight:700;color:#6B7280;
                            text-transform:uppercase;letter-spacing:.05em;margin-bottom:.4rem;">{label}</div>
                        <div style="font-size:1.5rem;font-weight:800;color:#1A1A2E;margin-bottom:.5rem;">
                            {unit}{cur_fmt}</div>
                        <div style="background:#F3F4F6;border-radius:999px;height:8px;overflow:hidden;">
                            <div style="width:{pct}%;height:100%;background:{color};border-radius:999px;
                                transition:width .4s ease;"></div>
                        </div>
                        <div style="font-size:.75rem;color:#9CA3AF;margin-top:.4rem;">
                            Hedef: {unit}{tgt_fmt} &nbsp;·&nbsp; <b style="color:{color};">{pct}%</b>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("&nbsp;")

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
        """<div class="info-box">Tüm metrikleri, cohort (müşteri grubu) matrisini ve müşteri segmentlerini
        tek sayfalık PDF raporu olarak indirin. Mağaza raporlaması veya arşivleme için idealdir.</div>""",
        unsafe_allow_html=True,
    )
    # PDF'i "Hazırla" tıklanınca üret ve session_state'e koy.
    # İndirme butonu blok DIŞINDA render edilir → rerun'da kaybolmaz,
    # bozuk/boş dosya servis edilmez (Streamlit download_button anti-pattern'i önlenir).
    if st.button("📄 PDF Raporu Hazırla", key="pdf_generate_btn"):
        with st.spinner("PDF hazırlanıyor…"):
            try:
                pdf_bytes = generate_report(user["id"], store_name, store_id)
                st.session_state["pdf_report"] = {
                    "bytes": bytes(pdf_bytes),
                    "store": store_name,
                    "store_id": store_id,
                }
            except Exception as e:
                st.session_state.pop("pdf_report", None)
                st.error(f"PDF oluşturulurken hata: {e}")

    # İndirme butonu — yalnızca aktif mağaza için üretilmiş PDF varsa göster
    _report = st.session_state.get("pdf_report")
    if _report and _report.get("store_id") == store_id and _report.get("bytes"):
        import re as _re
        safe_store = _re.sub(r"[^A-Za-z0-9_-]", "_", _report["store"]) or "magaza"
        fname = f"reorder_rapor_{safe_store}_{datetime.now().strftime('%Y%m%d')}.pdf"
        st.download_button(
            label="⬇️ PDF'i İndir",
            data=_report["bytes"],
            file_name=fname,
            mime="application/pdf",
            key="pdf_download_btn",
        )
        st.success("✅ PDF hazır! Yukarıdaki butona tıklayarak indirebilirsiniz.")


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Veri Yükle
# ─────────────────────────────────────────────────────────────────────────────
def show_upload() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    stores = st.session_state.get("stores", [])
    store_name = next((s["store_name"] for s in stores if s["id"] == store_id), user["store_name"])
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
                    imp = import_to_db(df, user["id"], store_id=store_id)
                _skipped_txt = f" ({imp['skipped']:,} tekrar atlandı.)" if imp['skipped'] else ""
                st.markdown(
                    f'<div class="success-box">✅ <b>{imp["inserted"]:,} yeni sipariş</b> aktarıldı.{_skipped_txt}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("📊 Analizlere Git"):
                    _go("dashboard")

    # ── Trendyol API ─────────────────────────────────────────────────────────
    with tab_api:
        creds = load_credentials(user["id"], store_id)

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
                    save_credentials(user["id"], seller_id, api_key, api_secret, store_id)
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
                            store_id,
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
                # Her mağaza farklı seed ve ürün listesiyle üretilir
                seed = (store_id or 42) % (2 ** 31)
                sample_df = generate_sample_orders(
                    n_customers=n_cust,
                    seed=seed,
                    store_name=store_name,
                )
                imp = import_to_db(sample_df, user["id"], batch="sample_data", store_id=store_id)
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

        m = _sm(user["id"], store_id)
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
                    cnt = delete_all_orders(user["id"], store_id)
                    st.success(f"{cnt:,} sipariş silindi.")
                    st.rerun()
        else:
            st.info("Henüz veri yüklenmemiş.")


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Analitik
# ─────────────────────────────────────────────────────────────────────────────
def show_analytics() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("📈", "Analitik", "Cohort (Müşteri Grubu) Retention, LTV ve Müşteri Davranışı")

    m = get_summary_metrics(user["id"], store_id)
    if not m["has_data"]:
        st.info("Veri bulunamadı. Lütfen önce sipariş yükleyin.")
        return

    tab_cohort, tab_ltv, tab_retention, tab_product = st.tabs(
        ["🔢 Cohort (Müşteri Grubu) Analizi", "💰 LTV Analizi", "📉 Retention Trendi", "📦 Ürün Analizi"]
    )

    # ── Cohort ───────────────────────────────────────────────────────────────
    with tab_cohort:
        _section("Aylık Cohort (Müşteri Grubu) Retention Matrisi")
        st.markdown(
            """<div class="info-box" style="font-size:.82rem;">
            Her satır bir <b>cohort</b> (müşteri grubu — o ay ilk kez alışveriş yapanlar).
            Sütunlar ilk alışverişten sonraki ayları gösterir.
            %100 = tüm cohort (müşteri grubu) o ayda aktifti.
            </div>""",
            unsafe_allow_html=True,
        )
        ret_df, cohort_sizes = get_cohort_retention(user["id"], store_id)
        if ret_df.empty:
            st.info("Cohort (müşteri grubu) analizi için en az 2 farklı müşteriye ihtiyaç var.")
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
                yaxis_title="Cohort (Müşteri Grubu) Ayı",
                template="plotly_white",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True)

            _section("Cohort (Müşteri Grubu) Boyutları")
            sizes_df = pd.DataFrame(
                {"Cohort (Müş. Grubu) Ayı": cohort_sizes.index.astype(str), "Müşteri Sayısı": cohort_sizes.values}
            )
            fig2 = px.bar(
                sizes_df,
                x="Cohort (Müş. Grubu) Ayı",
                y="Müşteri Sayısı",
                color_discrete_sequence=["#F27A1A"],
                template="plotly_white",
            )
            fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    # ── LTV ──────────────────────────────────────────────────────────────────
    with tab_ltv:
        ltv_df = get_ltv_distribution(user["id"], store_id)
        top10 = get_top_customers(user["id"], store_id=store_id)

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
        nvr = get_new_vs_returning(user["id"], store_id)
        trend = get_monthly_trend(user["id"], store_id)

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

    # ── Ürün Analizi ─────────────────────────────────────────────────────────
    with tab_product:
        prod = get_product_analysis(user["id"], store_id)

        if prod["retention"].empty:
            st.info("Ürün analizi için sipariş verilerinde ürün adı sütunu gereklidir.")
        else:
            _section("🔁 Ürün Başına Tekrar Alım Oranı")
            st.markdown(
                """<div class="info-box" style="font-size:.82rem;">
                Bir ürünü satın alan müşterilerin yüzde kaçı başka bir sipariş daha verdi?
                Yüksek oran → müşteri sadakatini tetikleyen ürün.
                </div>""",
                unsafe_allow_html=True,
            )

            ret_df = prod["retention"].copy()
            ret_df["product_label"] = ret_df["product_name"].apply(
                lambda x: x[:32] + "…" if len(str(x)) > 32 else x
            )

            c1, c2 = st.columns(2)
            with c1:
                _section("Alıcı Sayısına Göre")
                fig_ret = go.Figure(go.Bar(
                    x=ret_df["retention_rate"],
                    y=ret_df["product_label"],
                    orientation="h",
                    marker=dict(
                        color=ret_df["retention_rate"],
                        colorscale=[[0, "#FEE2E2"], [0.5, "#F27A1A"], [1, "#10B981"]],
                        showscale=False,
                    ),
                    text=ret_df["retention_rate"].apply(lambda v: f"%{v:.0f}"),
                    textposition="outside",
                    customdata=ret_df["buyer_count"],
                    hovertemplate="<b>%{y}</b><br>Tekrar: %{x}%<br>Alıcı: %{customdata}<extra></extra>",
                ))
                fig_ret.update_layout(
                    height=max(280, len(ret_df) * 30 + 60),
                    margin=dict(l=0, r=50, t=8, b=0),
                    xaxis=dict(title="Tekrar Alım %", ticksuffix="%", range=[0, 110]),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    template="plotly_white",
                )
                st.plotly_chart(fig_ret, use_container_width=True)

            with c2:
                _section("Müşteri Başı Ortalama Gelir")
                ltv_df = prod["ltv"].copy()
                ltv_df["product_label"] = ltv_df["product_name"].apply(
                    lambda x: x[:32] + "…" if len(str(x)) > 32 else x
                )
                fig_ltv = go.Figure(go.Bar(
                    x=ltv_df["avg_revenue_per_buyer"],
                    y=ltv_df["product_label"],
                    orientation="h",
                    marker=dict(color="#3B82F6"),
                    text=ltv_df["avg_revenue_per_buyer"].apply(lambda v: f"₺{v:,.0f}"),
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Ort. Gelir: ₺%{x:,.2f}<extra></extra>",
                ))
                fig_ltv.update_layout(
                    height=max(280, len(ltv_df) * 30 + 60),
                    margin=dict(l=0, r=70, t=8, b=0),
                    xaxis=dict(title="Müşteri Başı Gelir (₺)", tickprefix="₺"),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    template="plotly_white",
                )
                st.plotly_chart(fig_ltv, use_container_width=True)

            _section("📋 Ürün Detay Tablosu")
            tbl = ret_df[["product_name", "buyer_count", "repeat_buyers", "retention_rate", "total_revenue"]].copy()
            tbl.columns = ["Ürün", "Alıcı", "Tekrar Alıcı", "Tekrar Oranı (%)", "Toplam Gelir (₺)"]
            tbl["Toplam Gelir (₺)"] = tbl["Toplam Gelir (₺)"].apply(_fmt_tl)
            st.dataframe(tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Müşteri Segmentleri
# ─────────────────────────────────────────────────────────────────────────────
def show_segments() -> None:
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

    # ── Müşteri Listesi + Churn Score ────────────────────────────────────────
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

    show_cols = ["customer_identifier", "segment", "churn_score", "total_orders",
                 "total_revenue", "avg_order_value", "days_since_last"]
    col_rename = {
        "customer_identifier": "Müşteri",
        "segment":             "Segment",
        "churn_score":         "Churn Risk",
        "total_orders":        "Sipariş",
        "total_revenue":       "Toplam Harcama",
        "avg_order_value":     "Ort. Sipariş",
        "days_since_last":     "Son Alış. (Gün)",
    }
    display = (
        segments_df[show_cols]
        .rename(columns=col_rename)
        .sort_values("Churn Risk", ascending=False)
        .head(100)
        .reset_index(drop=True)
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
        styled = display.style.map(_color_churn, subset=["Churn Risk"])  # pandas >= 2.1
    except AttributeError:
        styled = display.style.applymap(_color_churn, subset=["Churn Risk"])  # pandas < 2.1
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Müşteri Detay ─────────────────────────────────────────────────────────
    st.markdown("&nbsp;")
    _section("👤 Müşteri Detay")
    all_customers = sorted(segments_df["customer_identifier"].tolist())
    selected_cust = st.selectbox(
        "Müşteri seç",
        options=["— Seçin —"] + all_customers,
        key="cust_detail_select",
    )

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

            # Özet kartlar
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Toplam Sipariş",   f"{detail['total_orders']}")
            d2.metric("Toplam Harcama",   _fmt_tl(detail["total_revenue"]))
            d3.metric("Ort. Sipariş",     _fmt_tl(detail["avg_order"]))
            d4.metric("Son Alışveriş",    f"{detail['days_since']} gün önce")
            d5.metric("İlk Alışveriş",    detail["first_date"])

            # Segment + Churn badge
            st.markdown(
                f"""<div style="margin:.6rem 0;">
                <span style="background:{seg_color}22;color:{seg_color};padding:5px 14px;
                    border-radius:20px;font-weight:700;font-size:.88rem;border:1px solid {seg_color}55;">
                    {detail['segment']}
                </span>
                &nbsp;
                <span style="background:{churn_color}22;color:{churn_color};padding:5px 14px;
                    border-radius:20px;font-weight:700;font-size:.88rem;border:1px solid {churn_color}55;">
                    🔥 Churn Risk: {churn}/100
                </span>
                </div>""",
                unsafe_allow_html=True,
            )

            # LTV Trendi
            gc1, gc2 = st.columns(2)
            with gc1:
                _section("📈 Kümülatif LTV Trendi")
                fig_ltv = go.Figure(go.Scatter(
                    x=detail["orders"]["date_str"],
                    y=detail["orders"]["cumulative_ltv"],
                    mode="lines+markers",
                    line=dict(color="#F27A1A", width=2.5),
                    marker=dict(size=7, color="#F27A1A"),
                    fill="tozeroy",
                    fillcolor="rgba(242,122,26,.1)",
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
                fig_m = px.bar(
                    detail["monthly"],
                    x="month_str", y="revenue",
                    color_discrete_sequence=["#3B82F6"],
                    labels={"month_str": "Ay", "revenue": "₺"},
                    template="plotly_white",
                )
                fig_m.update_layout(height=260, margin=dict(l=0, r=0, t=8, b=0))
                fig_m.update_xaxes(type="category")  # Period string'ini tarih olarak parse etmeyi önle
                st.plotly_chart(fig_m, use_container_width=True)

            # Sipariş tablosu
            _section("📋 Tüm Siparişler")
            ord_tbl = detail["orders"][["date_str", "order_number", "product_name", "quantity", "total_amount", "status"]].copy()
            ord_tbl.columns = ["Tarih", "Sipariş No", "Ürün", "Adet", "Tutar (₺)", "Durum"]
            ord_tbl["Tutar (₺)"] = ord_tbl["Tutar (₺)"].apply(_fmt_tl)
            st.dataframe(ord_tbl.sort_values("Tarih", ascending=False), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: E-posta Kampanyaları
# ─────────────────────────────────────────────────────────────────────────────
def show_campaigns() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("📧", "E-posta Kampanyaları", "Segment bazlı müşteri iletişimi")

    tab_smtp, tab_send, tab_history = st.tabs([
        "⚙️ SMTP Ayarları", "🚀 Kampanya Gönder", "📋 Geçmiş"
    ])

    # ── Sekme 1: SMTP Ayarları ────────────────────────────────────────────────
    with tab_smtp:
        existing = load_smtp_settings(user["id"])

        st.markdown("""
        <div class="info-box">
        ℹ️ <b>Gmail kullanıyorsanız:</b> Sunucu <code>smtp.gmail.com</code>, Port <b>587</b> (TLS).
        Normal şifre yerine
        <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:#1E40AF;">
        Uygulama Şifresi</a> oluşturmanız gerekir (2 Adımlı Doğrulama açık olmalı).
        </div>
        """, unsafe_allow_html=True)

        with st.form("smtp_form"):
            c1, c2 = st.columns([3, 1])
            smtp_host = c1.text_input(
                "SMTP Sunucu",
                value=existing.host if existing else "",
                placeholder="smtp.gmail.com",
            )
            smtp_port = c2.number_input(
                "Port",
                value=existing.port if existing else 587,
                min_value=1, max_value=65535,
            )
            smtp_user = st.text_input(
                "Kullanıcı Adı (E-posta)",
                value=existing.user if existing else "",
                placeholder="siz@gmail.com",
            )
            smtp_pass = st.text_input(
                "Şifre / Uygulama Şifresi",
                value=existing.password if existing else "",
                type="password",
            )
            c3, c4 = st.columns(2)
            smtp_from_email = c3.text_input(
                "Gönderen E-posta",
                value=existing.from_email if existing else "",
                placeholder="siz@gmail.com",
            )
            smtp_from_name = c4.text_input(
                "Gönderen Adı",
                value=existing.from_name if existing else user["store_name"],
            )

            col_save, col_test = st.columns(2)
            save_btn = col_save.form_submit_button("💾 Kaydet", use_container_width=True)
            test_btn = col_test.form_submit_button("📨 Test E-postası Gönder", use_container_width=True)

        if save_btn:
            if not smtp_host or not smtp_user or not smtp_pass:
                st.error("Sunucu, kullanıcı adı ve şifre zorunludur.")
            else:
                cfg = SMTPConfig(
                    host=smtp_host.strip(),
                    port=int(smtp_port),
                    user=smtp_user.strip(),
                    password=smtp_pass,
                    from_email=(smtp_from_email or smtp_user).strip(),
                    from_name=smtp_from_name or user["store_name"],
                )
                save_smtp_settings(user["id"], cfg)
                st.success("✅ SMTP ayarları kaydedildi!")
                st.rerun()

        if test_btn:
            if not smtp_host or not smtp_user or not smtp_pass:
                st.error("Önce bilgileri doldurun.")
            else:
                cfg = SMTPConfig(
                    host=smtp_host.strip(),
                    port=int(smtp_port),
                    user=smtp_user.strip(),
                    password=smtp_pass,
                    from_email=(smtp_from_email or smtp_user).strip(),
                    from_name=smtp_from_name or user["store_name"],
                )
                to_addr = (smtp_from_email or smtp_user).strip()
                with st.spinner("Test e-postası gönderiliyor…"):
                    result = send_test_email(cfg, to_addr)
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.error(result["message"])

    # ── Sekme 2: Kampanya Gönder ──────────────────────────────────────────────
    with tab_send:
        smtp_cfg = load_smtp_settings(user["id"])
        if not smtp_cfg:
            st.warning("⚠️ Önce **SMTP Ayarları** sekmesinden e-posta yapılandırmanızı tamamlayın.")
            return

        m = get_summary_metrics(user["id"], store_id)
        if not m["has_data"]:
            st.info("📂 Önce **Veri Yükle** sayfasından sipariş verisi yükleyin.")
            return

        segments_df = get_customer_segments(user["id"], store_id)
        if segments_df.empty:
            st.info("Yeterli müşteri verisi yok.")
            return

        seg_counts = segments_df.groupby("segment")["customer_identifier"].count().to_dict()
        targetable = ["Risk Altında", "Kaybolma Riski", "Tek Alışveriş", "Sadık Müşteri"]
        options = [s for s in targetable if seg_counts.get(s, 0) > 0]

        if not options:
            st.info("Kampanya gönderilebilecek segment bulunamadı.")
            return

        # Segment özet kartları
        _section("📊 Segment Durumu")
        cols_seg = st.columns(len(targetable))
        for i, seg in enumerate(targetable):
            tmpl_s = SEGMENT_TEMPLATES[seg]
            count = seg_counts.get(seg, 0)
            active = seg in options
            opacity = "1" if active else ".4"
            cols_seg[i].markdown(
                f"""<div style="background:{tmpl_s['color']}18;
                              border:1.5px solid {tmpl_s['color']}{'55' if active else '20'};
                              border-radius:10px;padding:14px;text-align:center;opacity:{opacity};">
                  <div style="font-size:1.5rem;">{tmpl_s['emoji']}</div>
                  <div style="font-weight:700;font-size:.82rem;color:{tmpl_s['color']};margin:5px 0 3px;">{seg}</div>
                  <div style="font-size:1.5rem;font-weight:700;color:#1a1a2e;">{count}</div>
                  <div style="font-size:.73rem;color:#9ca3af;">müşteri</div>
                </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("&nbsp;")

        chosen_seg = st.selectbox(
            "🎯 Hedef Segment",
            options,
            help="Hangi müşteri grubuna kampanya hazırlanacak?",
        )
        tmpl_c = SEGMENT_TEMPLATES[chosen_seg]
        st.markdown(
            f"<div style='color:{tmpl_c['color']};font-size:.84rem;margin:.3rem 0 .8rem;'>"
            f"📌 {tmpl_c['tanim']}</div>",
            unsafe_allow_html=True,
        )

        seg_customers = segments_df[segments_df["segment"] == chosen_seg].copy()

        # E-posta şablonu
        _section("📝 E-posta Şablonu")
        st.caption("**{musteri_adi}**, **{gun}** ve **{magaza_adi}** değişkenlerini kullanabilirsiniz.")
        custom_template = st.text_area(
            "Şablonu özelleştirin",
            value=tmpl_c["mesaj"],
            height=175,
            label_visibility="collapsed",
        )

        if not seg_customers.empty:
            first_c = seg_customers.iloc[0]
            preview = build_template(
                custom_template,
                first_c["customer_identifier"],
                int(first_c["days_since_last"]),
                user["store_name"],
            )
            with st.expander("👁️ Önizleme (1. müşteri için)"):
                st.text(preview)

        # WhatsApp şablonu
        _section("💬 WhatsApp Şablonu")
        wa_msg = tmpl_c["whatsapp"].replace("{magaza_adi}", user["store_name"])
        st.code(wa_msg, language=None)
        st.caption("Kopyalayıp Trendyol Sohbet veya WhatsApp Business'tan gönderebilirsiniz.")

        # CSV indirme
        _section("📥 Müşteri Listesi")
        export_df = seg_customers[
            ["customer_identifier", "segment", "total_orders", "total_revenue", "days_since_last"]
        ].copy()
        export_df["kisisel_mesaj"] = export_df.apply(
            lambda r: build_template(
                custom_template,
                r["customer_identifier"],
                int(r["days_since_last"]),
                user["store_name"],
            ),
            axis=1,
        )
        export_df.columns = [
            "Müşteri", "Segment", "Sipariş Sayısı",
            "Toplam Harcama (TL)", "Son Alışveriş (Gün)", "Kişisel Mesaj",
        ]
        csv_bytes = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        fname = f"kampanya_{chosen_seg.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"

        st.download_button(
            f"📥 {chosen_seg} Listesini İndir ({len(seg_customers)} müşteri)",
            data=csv_bytes,
            file_name=fname,
            mime="text/csv",
            use_container_width=True,
        )

        # E-posta raporu gönder
        _section("📨 E-posta Raporu Gönder")
        st.markdown(
            """<div class="info-box">ℹ️ Kampanya raporu <b>belirttiğiniz e-posta adresine</b> gönderilir.
            Raporda müşteri listesi ve kişiselleştirilmiş mesaj şablonu yer alır.
            Müşterilere Trendyol mesajlaşma veya WhatsApp üzerinden ulaşabilirsiniz.</div>""",
            unsafe_allow_html=True,
        )

        recipient = st.text_input(
            "Rapor alıcısı",
            value=user["email"],
            placeholder="ornek@email.com",
        )

        send_btn = st.button("🚀 Kampanya Raporu Gönder", type="primary", use_container_width=True)
        if send_btn:
            if not recipient:
                st.error("Alıcı e-posta adresi gereklidir.")
            else:
                customers_list = seg_customers.to_dict("records")
                with st.spinner("Kampanya raporu gönderiliyor…"):
                    result = send_campaign_report(
                        smtp_cfg,
                        recipient,
                        user["store_name"],
                        chosen_seg,
                        customers_list,
                        custom_template,
                    )
                if result["success"]:
                    st.success(result["message"])
                    save_campaign_log(
                        user["id"],
                        chosen_seg,
                        result["subject"],
                        recipient,
                        len(customers_list),
                        store_id,
                    )
                    st.balloons()
                else:
                    st.error(result["message"])

    # ── Sekme 3: Geçmiş ──────────────────────────────────────────────────────
    with tab_history:
        _section("📋 Kampanya Geçmişi")
        history = load_campaign_history(user["id"], store_id)
        if not history:
            st.info("Henüz kampanya gönderilmedi. **Kampanya Gönder** sekmesini kullanın.")
        else:
            df_hist = pd.DataFrame(history)
            df_hist.columns = ["Segment", "Konu", "Gönderilen E-posta", "Müşteri Sayısı", "Tarih"]
            if "Tarih" in df_hist.columns:
                df_hist["Tarih"] = (
                    pd.to_datetime(df_hist["Tarih"], errors="coerce")
                    .dt.strftime("%d.%m.%Y %H:%M")
                    .fillna("-")
                )
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            c1.metric("Toplam Kampanya", len(df_hist))
            c2.metric("Toplam Ulaşılan Müşteri", int(df_hist["Müşteri Sayısı"].sum()))


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa: Ayarlar
# ─────────────────────────────────────────────────────────────────────────────
def show_settings() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("⚙️", "Ayarlar", "Hesap ve mağaza bilgilerinizi yönetin")

    tab_account, tab_goals, tab_api = st.tabs(["👤 Hesap Bilgileri", "🎯 Hedefler", "🔌 Trendyol API (Pro)"])

    with tab_goals:
        _section("🎯 Aylık Hedefler")
        st.markdown(
            """<div class="info-box">Hedeflerinizi belirleyin — Dashboard'da ilerlemenizi progress bar olarak görün.</div>""",
            unsafe_allow_html=True,
        )
        cur_goals = load_goals(user["id"], store_id)
        with st.form("goals_form"):
            g1, g2, g3 = st.columns(3)
            gelir_h  = g1.number_input("💰 Aylık Gelir Hedefi (₺)", value=float(cur_goals.get("gelir", 0)), min_value=0.0, step=1000.0)
            musteri_h = g2.number_input("👤 Yeni Müşteri Hedefi", value=float(cur_goals.get("musterí", 0)), min_value=0.0, step=5.0)
            ret_h    = g3.number_input("🔄 Retention Oranı Hedefi (%)", value=float(cur_goals.get("retention", 0)), min_value=0.0, max_value=100.0, step=1.0)
            if st.form_submit_button("💾 Hedefleri Kaydet", use_container_width=True):
                new_goals = {}
                if gelir_h   > 0: new_goals["gelir"]     = gelir_h
                if musteri_h > 0: new_goals["musterí"]   = musteri_h
                if ret_h     > 0: new_goals["retention"] = ret_h
                save_goals(user["id"], store_id, new_goals)
                st.success("✅ Hedefler kaydedildi! Dashboard'da ilerlemenizi görebilirsiniz.")
                st.rerun()
        if cur_goals:
            st.markdown(
                '<div class="success-box">✅ Hedefler kayıtlı — Dashboard\'da "🎯 Bu Ay — Hedef Takibi" bölümünde görünür.</div>',
                unsafe_allow_html=True,
            )

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
        creds_s = load_credentials(user["id"], store_id)
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
                save_credentials(user["id"], s_seller, s_key, s_secret, store_id)
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
    elif page == "campaigns":
        show_campaigns()
    elif page == "settings":
        show_settings()
    else:
        show_dashboard()


main()
