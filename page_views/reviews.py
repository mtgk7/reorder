"""pages/reviews.py — Ürün Yorum Sentiment Analizi"""
from __future__ import annotations
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter

from src.ui_helpers import _header, _section, _plan_gate

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


def run() -> None:
    if not _plan_gate("campaigns"):  # Pro+ için
        return

    _header("💬", "Yorum Analizi", "Müşteri yorumlarından içgörü çıkarın")

    _section("📝 Yorumları Yapıştırın")
    st.markdown(
        """<div class="info-box">
        Trendyol ürün sayfanızdaki müşteri yorumlarını kopyalayıp buraya yapıştırın.
        Her yorum ayrı satırda olmalı. Sistem olumlu/olumsuz/nötr olarak sınıflandırır
        ve en sık geçen kelimeleri gösterir.
        </div>""",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        product_name = st.text_input("Ürün Adı (Opsiyonel)", placeholder="örn: Erkek Spor Ayakkabı")
    with col2:
        st.markdown("")

    reviews_text = st.text_area(
        "Yorumlar (her yorum ayrı satırda)",
        height=200,
        placeholder=(
            "Ürün çok güzel geldi, kalitesi harika...\n"
            "Beden uymadı, iade ettim...\n"
            "Fiyatına göre iyi..."
        ),
    )

    if st.button("🔍 Analiz Et", type="primary"):
        if not reviews_text.strip():
            st.error("Lütfen en az bir yorum girin.")
            return

        lines = [l.strip() for l in reviews_text.strip().split("\n") if l.strip()]
        if not lines:
            st.error("Geçerli yorum bulunamadı.")
            return

        results = []
        for review in lines:
            sentiment = _analyze_review(review)
            results.append({"yorum": review, "duygu": sentiment})

        df = pd.DataFrame(results)

        # Özet metrikler
        counts = df["duygu"].value_counts()
        pos = counts.get("Pozitif", 0)
        neg = counts.get("Negatif", 0)
        nor = counts.get("Nötr", 0)
        total = len(df)

        if product_name.strip():
            _section(f"📊 Sonuçlar — {product_name} — {total} Yorum")
        else:
            _section(f"📊 Sonuçlar — {total} Yorum")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam", total)
        c2.metric("✅ Pozitif", pos, f"%{pos / total * 100:.0f}")
        c3.metric("❌ Negatif", neg, f"%{neg / total * 100:.0f}")
        c4.metric("⚪ Nötr", nor, f"%{nor / total * 100:.0f}")

        # Pie chart
        if total > 0:
            fig = px.pie(
                values=[pos, neg, nor],
                names=["Pozitif", "Negatif", "Nötr"],
                color_discrete_map={
                    "Pozitif": "#10B981",
                    "Negatif": "#EF4444",
                    "Nötr": "#6B7280",
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

        # En sık geçen negatif kelimeler
        neg_reviews_text = " ".join(df[df["duygu"] == "Negatif"]["yorum"].tolist()).lower()
        if neg_reviews_text.strip():
            words = re.findall(r"\b[a-züğışçöı]{4,}\b", neg_reviews_text)
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

        # Yorum listesi
        _section("📋 Yorum Listesi")
        for _, row in df.iterrows():
            icon = (
                "✅" if row["duygu"] == "Pozitif"
                else "❌" if row["duygu"] == "Negatif"
                else "⚪"
            )
            st.markdown(f"{icon} {row['yorum']}")
