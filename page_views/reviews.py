"""pages/reviews.py — Ürün Yorum & Puan Analizi"""
from __future__ import annotations

import re
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter

from src.analytics import analyze_product_reviews
from src.database import (
    save_product_reviews, get_product_reviews, delete_all_product_reviews,
)
from src.ui_helpers import _header, _section, _kpi, _plan_gate

# ─── Türkçe sentiment keyword'leri ───────────────────────────────────────────
POSITIVE_WORDS = [
    "güzel", "harika", "mükemmel", "süper", "iyi", "kaliteli", "beğendim",
    "teşekkür", "hızlı", "sağlam", "uygun", "fiyat", "tavsiye", "memnun",
    "başarılı", "kusursuz", "şık", "sağlıklı", "gerçek", "orijinal",
]
NEGATIVE_WORDS = [
    "kötü", "berbat", "sahte", "bozuk", "yanlış", "eksik", "geç", "hatalı",
    "iade", "memnun değil", "çöp", "rezalet", "kaygı", "hayal kırıklığı",
    "kalitesiz", "dayanıksız", "renk farklı", "beden uymadı", "küçük", "büyük",
]


def _analyze_review(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if neg > pos:
        return "Negatif"
    elif pos > neg:
        return "Pozitif"
    return "Nötr"


def _parse_uploaded_file(uploaded) -> pd.DataFrame | None:
    """CSV veya Excel dosyasını DataFrame'e çevirir."""
    try:
        name = uploaded.name.lower()
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded, encoding="utf-8-sig")
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded)
        else:
            return None
        return df
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
        return None


def _detect_columns(df: pd.DataFrame) -> dict:
    """DataFrame sütunlarını otomatik eşleştirir."""
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def _find(candidates: list[str]) -> str | None:
        for c in candidates:
            if c in cols_lower:
                return cols_lower[c]
        return None

    return {
        "product_name": _find(["ürün adı", "urun_adi", "product_name", "product", "ürün", "urun"]),
        "rating":       _find(["puan", "rating", "yıldız", "yildiz", "star", "score", "değerlendirme"]),
        "review_text":  _find(["yorum", "review_text", "review", "metin", "comment", "açıklama"]),
        "review_date":  _find(["tarih", "date", "review_date", "yorum_tarihi"]),
    }


def run() -> None:
    if not _plan_gate("campaigns"):  # Pro+ için
        return

    user     = st.session_state.user
    store_id = st.session_state.get("active_store_id")

    _header("💬", "Yorum & Puan Analizi", "Ürün yorumlarından içgörü çıkarın")

    tab1, tab2 = st.tabs(["📂 CSV/Excel Import", "✏️ Manuel Yapıştır"])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: CSV / Excel Import
    # ─────────────────────────────────────────────────────────────────────────
    with tab1:
        st.markdown(
            """<div class="info-box">
            <b>Desteklenen format:</b> CSV (.csv) veya Excel (.xlsx/.xls)<br>
            <b>Gerekli sütunlar:</b> <code>ürün adı / product_name</code> ve <code>puan / rating</code> (1-5)<br>
            <b>Opsiyonel sütunlar:</b> <code>yorum / review_text</code> ve <code>tarih / review_date</code>
            </div>""",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Yorum dosyasını yükleyin",
            type=["csv", "xlsx", "xls"],
            key="review_file",
            label_visibility="collapsed",
        )

        if uploaded:
            df_raw = _parse_uploaded_file(uploaded)
            if df_raw is not None:
                col_map = _detect_columns(df_raw)

                st.markdown("**📋 Sütun Eşleştirmesi**")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    pname_col = st.selectbox(
                        "Ürün Adı Sütunu",
                        [None] + list(df_raw.columns),
                        index=(list(df_raw.columns).index(col_map["product_name"]) + 1
                               if col_map["product_name"] else 0),
                    )
                with c2:
                    rating_col = st.selectbox(
                        "Puan Sütunu (1-5)",
                        [None] + list(df_raw.columns),
                        index=(list(df_raw.columns).index(col_map["rating"]) + 1
                               if col_map["rating"] else 0),
                    )
                with c3:
                    text_col = st.selectbox(
                        "Yorum Metni (Opsiyonel)",
                        [None] + list(df_raw.columns),
                        index=(list(df_raw.columns).index(col_map["review_text"]) + 1
                               if col_map["review_text"] else 0),
                    )
                with c4:
                    date_col = st.selectbox(
                        "Tarih (Opsiyonel)",
                        [None] + list(df_raw.columns),
                        index=(list(df_raw.columns).index(col_map["review_date"]) + 1
                               if col_map["review_date"] else 0),
                    )

                st.caption(f"Dosyada {len(df_raw):,} satır bulundu.")
                st.dataframe(df_raw.head(5), use_container_width=True, hide_index=True)

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("📊 Analiz Et", type="primary", key="analyze_csv"):
                        if not rating_col:
                            st.error("Puan sütunu seçilmeli.")
                        else:
                            rows = []
                            for _, r in df_raw.iterrows():
                                rows.append({
                                    "product_name": str(r[pname_col]) if pname_col else "Genel",
                                    "rating":       r[rating_col],
                                    "review_text":  str(r[text_col]) if text_col else "",
                                    "review_date":  str(r[date_col]) if date_col else None,
                                })
                            result = analyze_product_reviews(rows)
                            st.session_state["_review_result"] = result
                            st.session_state["_review_rows"]   = rows

                with col_b:
                    if st.button("💾 Kaydet (DB)", key="save_csv"):
                        if not rating_col:
                            st.error("Puan sütunu seçilmeli.")
                        else:
                            rows = []
                            for _, r in df_raw.iterrows():
                                rows.append({
                                    "product_name": str(r[pname_col]) if pname_col else "Genel",
                                    "rating":       r[rating_col],
                                    "review_text":  str(r[text_col]) if text_col else "",
                                    "review_date":  str(r[date_col]) if date_col else None,
                                })
                            cnt = save_product_reviews(user["id"], store_id, rows)
                            st.success(f"✅ {cnt} yorum kaydedildi!")
                            result = analyze_product_reviews(rows)
                            st.session_state["_review_result"] = result

        # DB'den yükle
        db_reviews = get_product_reviews(user["id"], store_id)
        if db_reviews:
            st.markdown("&nbsp;")
            _section(f"📦 Kaydedilmiş Yorumlar ({len(db_reviews):,} kayıt)")
            if st.button("📊 Kaydedilen Yorumları Analiz Et", key="analyze_db"):
                result = analyze_product_reviews(db_reviews)
                st.session_state["_review_result"] = result
            if st.button("🗑️ Tüm Kayıtları Sil", key="del_all_reviews", type="secondary"):
                delete_all_product_reviews(user["id"], store_id)
                st.session_state.pop("_review_result", None)
                st.success("Tüm yorumlar silindi.")
                st.rerun()

        # Sonuçları göster
        result = st.session_state.get("_review_result")
        if result and result.get("has_data"):
            _show_analysis_results(result)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: Manuel Yapıştır
    # ─────────────────────────────────────────────────────────────────────────
    with tab2:
        st.markdown(
            """<div class="info-box">
            Trendyol ürün sayfanızdaki müşteri yorumlarını kopyalayıp yapıştırın.
            Her yorum ayrı satırda olmalı. Sistem otomatik duygu analizi yapar.
            </div>""",
            unsafe_allow_html=True,
        )

        col1, _ = st.columns([2, 1])
        with col1:
            product_name = st.text_input("Ürün Adı (Opsiyonel)", placeholder="örn: Erkek Spor Ayakkabı")

        reviews_text = st.text_area(
            "Yorumlar (her yorum ayrı satırda)",
            height=200,
            placeholder=(
                "Ürün çok güzel geldi, kalitesi harika...\n"
                "Beden uymadı, iade ettim...\n"
                "Fiyatına göre iyi..."
            ),
        )

        if st.button("🔍 Analiz Et", type="primary", key="analyze_manual"):
            if not reviews_text.strip():
                st.error("Lütfen en az bir yorum girin.")
            else:
                lines = [l.strip() for l in reviews_text.strip().split("\n") if l.strip()]
                if not lines:
                    st.error("Geçerli yorum bulunamadı.")
                else:
                    results = []
                    for review in lines:
                        sentiment = _analyze_review(review)
                        results.append({"yorum": review, "duygu": sentiment})

                    df = pd.DataFrame(results)
                    counts = df["duygu"].value_counts()
                    pos   = counts.get("Pozitif", 0)
                    neg   = counts.get("Negatif", 0)
                    nor   = counts.get("Nötr", 0)
                    total = len(df)

                    if product_name.strip():
                        _section(f"📊 Sonuçlar — {product_name} — {total} Yorum")
                    else:
                        _section(f"📊 Sonuçlar — {total} Yorum")

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Toplam", total)
                    c2.metric("✅ Pozitif", pos, f"%{pos/total*100:.0f}")
                    c3.metric("❌ Negatif", neg, f"%{neg/total*100:.0f}")
                    c4.metric("⚪ Nötr", nor, f"%{nor/total*100:.0f}")

                    if total > 0:
                        fig = px.pie(
                            values=[pos, neg, nor],
                            names=["Pozitif", "Negatif", "Nötr"],
                            color_discrete_map={
                                "Pozitif": "#10B981",
                                "Negatif": "#EF4444",
                                "Nötr":    "#6B7280",
                            },
                            hole=0.4,
                        )
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="#1A1A2E",
                            margin=dict(l=20, r=20, t=20, b=20),
                            height=260,
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    neg_text = " ".join(df[df["duygu"] == "Negatif"]["yorum"].tolist()).lower()
                    if neg_text.strip():
                        words = re.findall(r"\b[a-züğışçöı]{4,}\b", neg_text)
                        stop = {
                            "ürün", "çok", "ama", "için", "beni", "daha", "gibi", "bile",
                            "çünkü", "veya", "olan", "değil", "bunu", "çıktı", "geldi",
                        }
                        freq = Counter(w for w in words if w not in stop)
                        if freq:
                            _section("🔴 Negatif Yorumlarda En Sık Geçen Kelimeler")
                            freq_df = pd.DataFrame(freq.most_common(10), columns=["kelime", "adet"])
                            fig2 = px.bar(
                                freq_df, x="adet", y="kelime", orientation="h",
                                color_discrete_sequence=["#EF4444"],
                                template="plotly_white",
                            )
                            fig2.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="#1A1A2E",
                                margin=dict(l=10, r=10, t=10, b=10),
                                height=280,
                                yaxis=dict(autorange="reversed"),
                            )
                            st.plotly_chart(fig2, use_container_width=True)

                    _section("📋 Yorum Listesi")
                    for _, row in df.iterrows():
                        icon = "✅" if row["duygu"] == "Pozitif" else "❌" if row["duygu"] == "Negatif" else "⚪"
                        st.markdown(f"{icon} {row['yorum']}")


def _show_analysis_results(result: dict) -> None:
    """CSV/DB analizini görselleştirir."""
    _section(f"📊 Analiz Sonuçları — {result['total']:,} Yorum")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi("Toplam Yorum", str(result["total"]), icon="💬")
    with c2:
        avg = result["avg_rating"]
        color = "#10B981" if avg >= 4.0 else ("#F59E0B" if avg >= 3.0 else "#EF4444")
        _kpi("Ortalama Puan", f"{avg:.2f}/5", icon="⭐")
    with c3:
        _kpi("Negatif Yorum", str(result["neg_count"]),
             f"%{result['neg_count']/result['total']*100:.1f}" if result["total"] else "", icon="❌")
    with c4:
        pos_count = result["total"] - result["neg_count"]
        _kpi("Pozitif Yorum", str(pos_count),
             f"%{pos_count/result['total']*100:.1f}" if result["total"] else "", icon="✅")

    # Puan Dağılımı
    dist = result.get("dist")
    if dist is not None and not dist.empty:
        _section("⭐ Puan Dağılımı")
        colors_dist = {1: "#EF4444", 2: "#F97316", 3: "#F59E0B", 4: "#84CC16", 5: "#10B981"}
        dist["renk"] = dist["puan"].map(colors_dist).fillna("#CBD5E1")
        fig = px.bar(
            dist,
            x="puan",
            y="adet",
            color="puan",
            color_discrete_map={k: v for k, v in colors_dist.items()},
            labels={"puan": "Puan", "adet": "Yorum Sayısı"},
            template="plotly_white",
            text="adet",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            showlegend=False,
            margin=dict(l=10, r=10, t=20, b=10),
            height=280,
            xaxis=dict(tickvals=[1, 2, 3, 4, 5], title="Puan (1-5)"),
            yaxis=dict(gridcolor="#F1F5F9"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Ürün Bazlı Puan
    by_product = result.get("by_product")
    if by_product is not None and not by_product.empty:
        _section("🛍️ Ürün Bazlı Ortalama Puan")
        prod_chart = by_product.head(15).copy()
        prod_chart["ürün"] = prod_chart["product_name"].str[:40]
        fig2 = px.bar(
            prod_chart,
            x="ort_puan",
            y="ürün",
            orientation="h",
            color="ort_puan",
            color_continuous_scale=["#EF4444", "#F59E0B", "#10B981"],
            range_color=[1, 5],
            text="ort_puan",
            labels={"ort_puan": "Ort. Puan", "ürün": ""},
            template="plotly_white",
        )
        fig2.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            coloraxis_showscale=False,
            margin=dict(l=10, r=50, t=10, b=10),
            height=max(280, len(prod_chart) * 38),
            yaxis=dict(autorange="reversed"),
            xaxis=dict(range=[0, 5.5]),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Negatif oran
        high_neg = by_product[by_product["negatif_oran"] > 20]
        if not high_neg.empty:
            st.markdown(
                f"""<div style="background:#FEF2F2;border:1px solid #FECACA;border-left:4px solid #EF4444;
                border-radius:8px;padding:.8rem 1rem;margin:.5rem 0;">
                ⚠️ <b style="color:#991B1B;">Yüksek Negatif Yorum Oranı Olan Ürünler:</b><br>
                <span style="font-size:.88rem;color:#7F1D1D;">
                {', '.join(high_neg['product_name'].str[:30].tolist()[:5])}
                </span></div>""",
                unsafe_allow_html=True,
            )

    # Negatif Kelimeler
    neg_kw = result.get("neg_keywords")
    if neg_kw is not None and not neg_kw.empty:
        _section("🔴 Negatif Yorumlarda En Sık Kelimeler")
        fig3 = px.bar(
            neg_kw,
            x="adet",
            y="kelime",
            orientation="h",
            color_discrete_sequence=["#EF4444"],
            labels={"adet": "Adet", "kelime": ""},
            template="plotly_white",
            text="adet",
        )
        fig3.update_traces(textposition="outside")
        fig3.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=40, t=10, b=10),
            height=max(280, len(neg_kw) * 30),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # Puan Trendi
    trend = result.get("trend")
    if trend is not None and not trend.empty and len(trend) > 1:
        _section("📅 Aylık Puan Trendi")
        fig4 = px.line(
            trend,
            x="ay",
            y="ort_puan",
            markers=True,
            color_discrete_sequence=["#F27A1A"],
            labels={"ay": "Ay", "ort_puan": "Ortalama Puan"},
            template="plotly_white",
        )
        fig4.update_traces(line_width=2.5, marker_size=7)
        fig4.add_hline(y=4.0, line_dash="dash", line_color="#10B981",
                       annotation_text="Hedef: 4.0", annotation_position="right")
        fig4.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1A1A2E",
            margin=dict(l=10, r=60, t=20, b=10),
            height=260,
            yaxis=dict(range=[1, 5.2], gridcolor="#F1F5F9"),
            xaxis=dict(tickangle=-30),
        )
        st.plotly_chart(fig4, use_container_width=True)
