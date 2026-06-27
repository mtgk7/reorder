"""page_views/stock_alerts.py — Stok Uyarı Sistemi"""
from __future__ import annotations

import streamlit as st
import plotly.express as px

from src.analytics import get_stock_burnout
from src.database import (
    save_stock_alert, get_stock_alerts as _db_get_alerts, delete_stock_alert,
)
from src.ui_helpers import _header, _section, _kpi, _plan_gate, _fmt_tl


def run() -> None:
    if not _plan_gate("stock_alerts"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("📦", "Stok Uyarı Sistemi", "Satış hızına göre tükenme tahmini")

    # ── Yeni Ürün Ekle ────────────────────────────────────────────────────────
    _section("➕ Ürün ve Stok Miktarı Gir")

    with st.form("stock_form", border=False):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            product_name = st.text_input(
                "Ürün Adı",
                placeholder="örn: Erkek Spor Ayakkabı Model-X",
                help="Sipariş verilerindeki ürün adıyla eşleşmeli (kısmi eşleşme de çalışır)",
            )
        with c2:
            stock_qty = st.number_input("Stok Miktarı (adet)", min_value=0, value=100, step=1)
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Ekle", type="primary", use_container_width=True)

    if submitted:
        if not product_name.strip():
            st.error("Ürün adı boş olamaz.")
        else:
            save_stock_alert(user["id"], store_id, product_name.strip(), int(stock_qty))
            st.success(f"✅ '{product_name}' stok uyarısına eklendi!")
            st.rerun()

    # ── Mevcut Stok Durumu ────────────────────────────────────────────────────
    alerts_raw = _db_get_alerts(user["id"], store_id)

    if not alerts_raw:
        st.markdown(
            """<div class="info-box">📦 Henüz stok uyarısı eklenmedi.
            Yukarıdaki formu kullanarak ürün adını ve mevcut stok miktarını girin.
            Sistem, sipariş geçmişinizden satış hızını hesaplayarak kaç günde tükeneceğini tahmin eder.</div>""",
            unsafe_allow_html=True,
        )
        return

    # Hesapla
    burnout = get_stock_burnout(user["id"], store_id, alerts_raw)

    if not burnout:
        st.info("Stok hesaplaması için yeterli sipariş verisi bulunamadı.")
        return

    # ── KPI Özeti ─────────────────────────────────────────────────────────────
    _section("📊 Stok Durumu Özeti")

    kritik  = sum(1 for b in burnout if b["status"] == "kritik")
    uyari   = sum(1 for b in burnout if b["status"] == "uyari")
    normal  = sum(1 for b in burnout if b["status"] == "normal")
    bilinmiyor = sum(1 for b in burnout if b["status"] == "bilinmiyor")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi("Kritik (< 7 gün)", str(kritik), "⚠️ Acil sipariş gerekli", icon="🔴")
    with c2:
        _kpi("Uyarı (7-14 gün)", str(uyari), "Sipariş planla", icon="🟡")
    with c3:
        _kpi("Normal (> 14 gün)", str(normal), "Stok yeterli", icon="🟢")
    with c4:
        _kpi("Bilinmiyor", str(bilinmiyor), "Satış verisi yok", icon="⚪")

    # ── Tablo ─────────────────────────────────────────────────────────────────
    _section("📋 Ürün Bazlı Tükenme Tahmini")

    status_colors = {
        "kritik":     "🔴",
        "uyari":      "🟡",
        "normal":     "🟢",
        "bilinmiyor": "⚪",
    }
    status_labels = {
        "kritik":     "KRİTİK",
        "uyari":      "UYARI",
        "normal":     "NORMAL",
        "bilinmiyor": "VERİ YOK",
    }

    for item in burnout:
        icon     = status_colors.get(item["status"], "⚪")
        slabel   = status_labels.get(item["status"], item["status"])
        days_txt = f"{int(item['days_remaining'])} gün" if item["days_remaining"] is not None else "—"

        # Renk
        if item["status"] == "kritik":
            bg = "#FEF2F2"; border = "#EF4444"; text_color = "#991B1B"
        elif item["status"] == "uyari":
            bg = "#FFFBEB"; border = "#F59E0B"; text_color = "#92400E"
        elif item["status"] == "normal":
            bg = "#ECFDF5"; border = "#10B981"; text_color = "#065F46"
        else:
            bg = "#F3F4F6"; border = "#9CA3AF"; text_color = "#374151"

        st.markdown(
            f"""<div style="background:{bg};border:1px solid {border};border-left:4px solid {border};
            border-radius:10px;padding:.9rem 1.2rem;margin:.35rem 0;
            display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;">
                <div style="flex:1;min-width:200px;">
                    <span style="font-size:1rem;margin-right:.4rem;">{icon}</span>
                    <b style="color:#1A1A2E;font-size:.92rem;">{item['product_name']}</b>
                    <span style="background:{border}22;color:{border};border:1px solid {border}66;
                        border-radius:20px;font-size:.68rem;font-weight:700;padding:.12rem .5rem;
                        margin-left:.5rem;">{slabel}</span>
                </div>
                <div style="display:flex;gap:1.5rem;flex-wrap:wrap;">
                    <div style="text-align:center;">
                        <div style="font-size:.68rem;color:#6B7280;text-transform:uppercase;font-weight:600;">Stok</div>
                        <div style="font-size:1rem;font-weight:800;color:{text_color};">{item['stock_quantity']:,} adet</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:.68rem;color:#6B7280;text-transform:uppercase;font-weight:600;">Günlük Satış</div>
                        <div style="font-size:1rem;font-weight:800;color:{text_color};">{item['daily_rate']:.2f} adet/gün</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:.68rem;color:#6B7280;text-transform:uppercase;font-weight:600;">Tahmini Süre</div>
                        <div style="font-size:1rem;font-weight:800;color:{text_color};">{days_txt}</div>
                    </div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Grafik ────────────────────────────────────────────────────────────────
    items_with_days = [b for b in burnout if b["days_remaining"] is not None]
    if items_with_days:
        _section("📉 Tükenme Süresi Grafiği")
        import pandas as pd
        chart_df = pd.DataFrame(items_with_days)
        chart_df["ürün"] = chart_df["product_name"].str[:35]
        chart_df["renk"] = chart_df["status"].map(
            {"kritik": "#EF4444", "uyari": "#F59E0B", "normal": "#10B981", "bilinmiyor": "#9CA3AF"}
        )
        fig = px.bar(
            chart_df.sort_values("days_remaining"),
            x="days_remaining",
            y="ürün",
            orientation="h",
            color="status",
            color_discrete_map={
                "kritik": "#EF4444", "uyari": "#F59E0B",
                "normal": "#10B981", "bilinmiyor": "#9CA3AF",
            },
            labels={"days_remaining": "Tahmini Gün", "ürün": "", "status": "Durum"},
            template="plotly_white",
        )
        fig.add_vline(x=7,  line_dash="dash", line_color="#EF4444", annotation_text="Kritik (7 gün)")
        fig.add_vline(x=14, line_dash="dash", line_color="#F59E0B", annotation_text="Uyarı (14 gün)")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=10, t=20, b=10),
            height=max(280, len(items_with_days) * 42),
            yaxis=dict(autorange="reversed"),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Ürün Sil ──────────────────────────────────────────────────────────────
    _section("🗑️ Stok Uyarısı Sil")
    options = {f"{b['product_name']} (ID:{b['id']})": b["id"] for b in burnout}
    to_delete = st.selectbox("Silinecek ürün", options=list(options.keys()), label_visibility="collapsed")
    if st.button("🗑️ Sil", key="del_stock", type="secondary"):
        delete_stock_alert(options[to_delete], user["id"])
        st.success("Stok uyarısı silindi.")
        st.rerun()
