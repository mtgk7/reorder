"""
ui_helpers.py — ReOrder paylaşılan UI sabitleri ve yardımcı fonksiyonlar.
Her sayfa dosyası buradan import eder.
"""
from __future__ import annotations
import streamlit as st

# ─── Plan sabitleri ───────────────────────────────────────────────────────────

_PLAN_LIMITS = {
    "Starter": {
        "max_stores":    1,
        "segments":      True,
        "campaigns":     False,
        "pdf_report":    False,
        "trendyol_api":  False,
        "weekly_report": False,
        "analytics_tabs": ["cohort", "return"],
    },
    "Pro": {
        "max_stores":    3,
        "segments":      True,
        "campaigns":     True,
        "pdf_report":    True,
        "trendyol_api":  False,
        "weekly_report": True,
        "analytics_tabs": ["cohort", "ltv", "retention", "product", "forecast", "crosssell", "return", "hourly", "city"],
    },
    "Enterprise": {
        "max_stores":    None,
        "segments":      True,
        "campaigns":     True,
        "pdf_report":    True,
        "trendyol_api":  True,
        "weekly_report": True,
        "analytics_tabs": ["cohort", "ltv", "retention", "product", "forecast", "crosssell", "return", "hourly", "city"],
    },
}

_PLAN_BADGE_COLOR = {"Starter": "#6B7280", "Pro": "#F27A1A", "Enterprise": "#8B5CF6"}
_PLAN_UPGRADE     = {"Starter": "Pro", "Pro": "Enterprise", "Enterprise": None}

_PLAN_PRICES = {
    "m": {"Starter": (349, "/ay"), "Pro": (699, "/ay"), "Enterprise": (1249, "/ay")},
    "q": {"Starter": (875, "/3 ay"), "Pro": (1875, "/3 ay"), "Enterprise": (3550, "/3 ay")},
    "y": {"Starter": (2699, "/yıl"), "Pro": (6900, "/yıl"), "Enterprise": (12000, "/yıl")},
}
_PLAN_FEATURES = {
    "Starter":    ["1 Mağaza", "Dashboard & KPI", "Cohort Analizi", "PDF Rapor", "Temel E-posta Desteği"],
    "Pro":        ["3 Mağaza", "Dashboard & KPI", "Cohort + RFM", "PDF Rapor", "E-posta Kampanya", "Öncelikli Destek"],
    "Enterprise": ["Sınırsız Mağaza", "Tüm Pro Özellikler", "Trendyol API Entegrasyonu", "Öncelikli Destek", "Özel Hesap Yöneticisi"],
}

_ONBOARDING_BG = """
<div id="ob-bg" style="position:fixed;top:0;left:0;width:100vw;height:100vh;
background:linear-gradient(145deg,#0a2533,#0d3a4b,#134e5e,#0a2e3d);z-index:-1;pointer-events:none;"></div>
"""

# ─── Plan yardımcıları ────────────────────────────────────────────────────────

def _plan_limits() -> dict:
    plan = st.session_state.get("user", {}).get("plan", "Starter")
    return _PLAN_LIMITS.get(plan, _PLAN_LIMITS["Starter"])


def _plan_gate(feature: str) -> bool:
    limits = _plan_limits()
    if limits.get(feature, False):
        return True
    _plan_order = ["Starter", "Pro", "Enterprise"]
    min_plan = next(
        (p for p in _plan_order if _PLAN_LIMITS.get(p, {}).get(feature, False)),
        None,
    )
    if min_plan:
        st.warning(
            f"Bu özellik **{min_plan}** ve üzeri planlarda kullanılabilir. "
            f"Planınızı yükseltmek için **Ayarlar → Plan Yönetimi** sayfasını ziyaret edin."
        )
    return False

# ─── Render yardımcıları ──────────────────────────────────────────────────────

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


_PAGE_MAP = {
    "dashboard": "page_views/dashboard.py",
    "upload":    "page_views/upload.py",
    "analytics": "page_views/analytics.py",
    "segments":  "page_views/segments.py",
    "campaigns": "page_views/campaigns.py",
    "settings":  "page_views/settings.py",
    "reviews":   "page_views/reviews.py",
}


def _go(page: str) -> None:
    """Belirtilen sayfaya geçer (session_state + rerun)."""
    st.session_state.page = page
    st.rerun()
