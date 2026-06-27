"""page_views/competitor_prices.py — Rakip Fiyat Takibi"""
from __future__ import annotations

import streamlit as st
import plotly.express as px
import pandas as pd

from src.database import (
    save_competitor_price, get_competitor_prices, delete_competitor_price,
)
from src.ui_helpers import _header, _section, _kpi, _fmt_tl, _plan_gate


def _position_label(my: float, comp: float) -> tuple[str, str]:
    """Fiyat pozisyonunu döndürür: (etiket, renk)"""
    if my < comp * 0.95:
        return "EN UCUZ ✅", "#10B981"
    elif my > comp * 1.05:
        return "PAHALI ⚠️", "#EF4444"
    else:
        return "ORTA ↔️", "#F59E0B"


def run() -> None:
    if not _plan_gate("competitor_prices"):
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("🏷️", "Rakip Fiyat Takibi", "Kendi fiyatınızı rakiplerinizle karşılaştırın")

    tab_manual, tab_import = st.tabs(["✏️ Manuel Giriş", "📂 Trendyol'dan İçe Aktar"])

    with tab_import:
        st.markdown(
            """<div class="info-box">
            Trendyol Satıcı Paneli'nden rakip fiyat listesini indirip buraya yükleyin.<br><br>
            1️⃣ <a href="https://partner.trendyol.com" target="_blank"><b>partner.trendyol.com</b></a> → Giriş Yap<br>
            2️⃣ <b>Ürünlerim → Fiyat Güncelleme</b> ya da <b>Rakip Fiyatları</b> menüsüne git<br>
            3️⃣ <b>Excel'e Aktar</b> → İndirilen dosyayı aşağıya yükle<br><br>
            <b>Desteklenen sütunlar:</b> <code>ürün adı</code>, <code>benim fiyatım</code>,
            <code>rakip adı</code>, <code>rakip fiyatı</code>
            </div>""",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader("Fiyat dosyası (.csv / .xlsx)", type=["csv","xlsx","xls"],
                                    key="price_import_file", label_visibility="collapsed")
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df_imp = pd.read_csv(uploaded)
                else:
                    df_imp = pd.read_excel(uploaded)

                df_imp.columns = [str(c).strip().lower() for c in df_imp.columns]

                def _find(candidates):
                    for c in candidates:
                        if c in df_imp.columns:
                            return c
                    return None

                pname_col  = _find(["ürün adı","urun adi","product_name","ürün","urun","product"])
                my_col     = _find(["benim fiyatım","benim fiyatim","my_price","kendi fiyat","satış fiyatı","satis fiyati"])
                comp_col   = _find(["rakip adı","rakip adi","competitor_name","rakip mağaza","rakip magaza","satici"])
                cprice_col = _find(["rakip fiyatı","rakip fiyati","competitor_price","rakip fiyat"])

                st.caption(f"{len(df_imp):,} satır bulundu. Sütunlar: {list(df_imp.columns)}")

                c1, c2, c3, c4 = st.columns(4)
                pname_col  = c1.selectbox("Ürün Adı", [None]+list(df_imp.columns), index=(list(df_imp.columns).index(pname_col)+1 if pname_col else 0))
                my_col     = c2.selectbox("Benim Fiyatım", [None]+list(df_imp.columns), index=(list(df_imp.columns).index(my_col)+1 if my_col else 0))
                comp_col   = c3.selectbox("Rakip Adı", [None]+list(df_imp.columns), index=(list(df_imp.columns).index(comp_col)+1 if comp_col else 0))
                cprice_col = c4.selectbox("Rakip Fiyatı", [None]+list(df_imp.columns), index=(list(df_imp.columns).index(cprice_col)+1 if cprice_col else 0))

                if st.button("💾 İçe Aktar", type="primary", key="import_prices"):
                    if not all([pname_col, my_col, comp_col, cprice_col]):
                        st.error("Tüm sütunları seçin.")
                    else:
                        saved = 0
                        for _, row in df_imp.iterrows():
                            try:
                                save_competitor_price(
                                    user["id"], store_id,
                                    str(row[pname_col]),
                                    float(str(row[my_col]).replace(",",".")),
                                    str(row[comp_col]),
                                    float(str(row[cprice_col]).replace(",",".")),
                                    comp_url="",
                                )
                                saved += 1
                            except Exception:
                                continue
                        st.success(f"✅ {saved} rakip fiyatı içe aktarıldı!")
                        st.rerun()
            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")

    with tab_manual:
        _section("➕ Yeni Rakip Fiyatı Gir")
        st.markdown(
            """<div class="info-box">
            Rakip ürün URL'si ve fiyatını manuel olarak girin. Sistem fiyat pozisyonunuzu
            (en ucuz / orta / pahalı) hesaplar ve zaman içinde değişimi takip eder.
            </div>""",
            unsafe_allow_html=True,
        )

        with st.form("competitor_form", border=False):
            c1, c2 = st.columns(2)
            with c1:
                product_name = st.text_input("Ürün Adı", placeholder="örn: Çocuk Bisikleti 24\"")
                my_price     = st.number_input("Benim Fiyatım (₺)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            with c2:
                comp_name    = st.text_input("Rakip Mağaza Adı", placeholder="örn: ABC Mağazası")
                comp_price   = st.number_input("Rakip Fiyatı (₺)", min_value=0.0, value=0.0, step=0.01, format="%.2f")

            comp_url = st.text_input("Rakip Ürün URL (Opsiyonel)", placeholder="https://www.trendyol.com/...")
            submitted = st.form_submit_button("Kaydet", type="primary", use_container_width=True)

        if submitted:
            if not product_name.strip():
                st.error("Ürün adı boş olamaz.")
            elif my_price <= 0 or comp_price <= 0:
                st.error("Fiyatlar sıfırdan büyük olmalı.")
            elif not comp_name.strip():
                st.error("Rakip mağaza adı girin.")
            else:
                save_competitor_price(
                    user["id"], store_id, product_name, my_price, comp_name, comp_price, comp_url or ""
                )
                st.success(f"✅ '{product_name}' için rakip fiyatı kaydedildi!")
                st.rerun()

    # ── Mevcut Karşılaştırma Tablosu ──────────────────────────────────────────
    prices = get_competitor_prices(user["id"], store_id)

    if not prices:
        st.markdown(
            """<div class="info-box">📭 Henüz rakip fiyatı eklenmedi.
            Yukarıdaki formu kullanarak ürünlerinizi ve rakiplerinizi ekleyin.</div>""",
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(prices)

    # ── KPI ───────────────────────────────────────────────────────────────────
    _section("📊 Fiyat Pozisyon Özeti")

    df["pozisyon"] = df.apply(
        lambda r: _position_label(r["my_price"], r["competitor_price"])[0], axis=1
    )
    df["poz_renk"] = df.apply(
        lambda r: _position_label(r["my_price"], r["competitor_price"])[1], axis=1
    )
    df["fark_pct"] = ((df["my_price"] - df["competitor_price"]) / df["competitor_price"] * 100).round(1)

    ucuz  = (df["fark_pct"] < -5).sum()
    orta  = (df["fark_pct"].between(-5, 5)).sum()
    pahali = (df["fark_pct"] > 5).sum()

    c1, c2, c3 = st.columns(3)
    with c1:
        _kpi("En Ucuz Ürün", str(ucuz), "Rakipten daha uygun fiyatlı", icon="✅")
    with c2:
        _kpi("Orta Segment", str(orta), "±%5 fiyat aralığında", icon="↔️")
    with c3:
        _kpi("Pahalı Ürün", str(pahali), "Fiyat rekabeti gerekli", icon="⚠️")

    # ── Detay Kartları ────────────────────────────────────────────────────────
    _section("🏷️ Ürün Bazlı Karşılaştırma")

    for _, row in df.iterrows():
        pos_label, pos_color = _position_label(float(row["my_price"]), float(row["competitor_price"]))
        fark = float(row["my_price"]) - float(row["competitor_price"])
        fark_txt = f"+{_fmt_tl(abs(fark))} daha pahalı" if fark > 0 else (
            f"{_fmt_tl(abs(fark))} daha ucuz" if fark < 0 else "Eşit fiyat"
        )

        url_html = ""
        if row.get("competitor_url"):
            url_html = f'<a href="{row["competitor_url"]}" target="_blank" style="color:#3B82F6;font-size:.78rem;">🔗 Rakip Sayfası</a>'

        st.markdown(
            f"""<div style="background:white;border:1px solid #E2E8F0;border-radius:12px;
            padding:.9rem 1.2rem;margin:.35rem 0;box-shadow:0 1px 4px rgba(0,0,0,.06);">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;">
                    <div>
                        <b style="font-size:.92rem;color:#1A1A2E;">{row['product_name']}</b>
                        <span style="background:{pos_color}22;color:{pos_color};border:1px solid {pos_color}66;
                            border-radius:20px;font-size:.66rem;font-weight:700;padding:.1rem .45rem;margin-left:.5rem;">
                            {pos_label}
                        </span>
                        <br><span style="font-size:.75rem;color:#6B7280;">vs <b>{row['competitor_name']}</b></span>
                        {'<br>' + url_html if url_html else ''}
                    </div>
                    <div style="display:flex;gap:1.5rem;flex-wrap:wrap;">
                        <div style="text-align:center;">
                            <div style="font-size:.66rem;color:#6B7280;font-weight:600;text-transform:uppercase;">Benim</div>
                            <div style="font-size:1.1rem;font-weight:800;color:#F27A1A;">{_fmt_tl(row['my_price'])}</div>
                        </div>
                        <div style="text-align:center;">
                            <div style="font-size:.66rem;color:#6B7280;font-weight:600;text-transform:uppercase;">Rakip</div>
                            <div style="font-size:1.1rem;font-weight:800;color:#1A1A2E;">{_fmt_tl(row['competitor_price'])}</div>
                        </div>
                        <div style="text-align:center;">
                            <div style="font-size:.66rem;color:#6B7280;font-weight:600;text-transform:uppercase;">Fark</div>
                            <div style="font-size:.88rem;font-weight:700;color:{pos_color};">{fark_txt}</div>
                        </div>
                    </div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Grafik ────────────────────────────────────────────────────────────────
    if len(df) > 1:
        _section("📉 Fiyat Karşılaştırma Grafiği")
        chart_df = df.copy()
        chart_df["ürün"] = chart_df["product_name"].str[:30]
        melted = pd.melt(
            chart_df,
            id_vars=["ürün"],
            value_vars=["my_price", "competitor_price"],
            var_name="Kaynak",
            value_name="Fiyat",
        )
        melted["Kaynak"] = melted["Kaynak"].map({"my_price": "Benim Fiyatım", "competitor_price": "Rakip Fiyatı"})
        fig = px.bar(
            melted,
            x="Fiyat",
            y="ürün",
            color="Kaynak",
            barmode="group",
            orientation="h",
            color_discrete_map={"Benim Fiyatım": "#F27A1A", "Rakip Fiyatı": "#CBD5E1"},
            template="plotly_white",
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=10, t=20, b=10),
            height=max(280, len(df) * 52),
            yaxis=dict(autorange="reversed"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Sil ───────────────────────────────────────────────────────────────────
    _section("🗑️ Kayıt Sil")
    opts = {f"{r['product_name']} vs {r['competitor_name']} (ID:{r['id']})": r["id"] for _, r in df.iterrows()}
    to_del = st.selectbox("Silinecek kayıt", options=list(opts.keys()), label_visibility="collapsed")
    if st.button("🗑️ Sil", key="del_comp", type="secondary"):
        delete_competitor_price(opts[to_del], user["id"])
        st.success("Kayıt silindi.")
        st.rerun()
