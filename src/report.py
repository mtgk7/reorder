"""
report.py — PDF rapor üreteci.
Dashboard metriklerini, aylık trend grafiğini, cohort matrisini
ve müşteri segmentlerini tek bir A4 PDF dosyasına aktarır.
"""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # Ekransız backend
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fpdf import FPDF

from src.analytics import (
    get_cohort_retention,
    get_customer_segments,
    get_monthly_trend,
    get_summary_metrics,
    get_top_customers,
)

# ─────────────────────────────────────────────────────────────────────────────
# Renk sabitleri (RGB tuple)
# ─────────────────────────────────────────────────────────────────────────────
_ORANGE   = (242, 122,  26)
_DARK     = ( 26,  26,  46)
_GRAY     = (107, 114, 128)
_LIGHT    = (248, 250, 252)
_GREEN    = ( 16, 185, 129)
_YELLOW   = (251, 191,  36)
_RED      = (239,  68,  68)
_BLUE     = ( 59, 130, 246)
_WHITE    = (255, 255, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Türkçe → ASCII dönüştürücü (PDF font uyumluluğu)
# ─────────────────────────────────────────────────────────────────────────────
def _tr(text: str) -> str:
    """Türkçe ve latin-1 dışı karakterleri ASCII karşılıklarına çevirir."""
    s = str(text)
    s = s.translate(str.maketrans("ğĞşŞıİüÜöÖçÇ", "gGsSimuUoOcC"))
    # Em-dash, en-dash ve diğer latin-1 dışı karakterleri değiştir
    s = s.replace("—", "-").replace("–", "-").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"').replace("…", "...")
    # Kalan latin-1 dışı karakterleri kaldır
    return s.encode("latin-1", errors="ignore").decode("latin-1")


# ─────────────────────────────────────────────────────────────────────────────
# PDF sınıfı
# ─────────────────────────────────────────────────────────────────────────────
class _ReOrderPDF(FPDF):
    def __init__(self, store_name: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.store_name  = _tr(store_name)[:28]
        self.report_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=15, top=22, right=15)

    # ── Üstbilgi ──────────────────────────────────────────────────────────────
    def header(self) -> None:
        self.set_fill_color(*_ORANGE)
        self.rect(0, 0, 210, 17, style="F")
        self.set_font("Helvetica", style="B", size=11)
        self.set_text_color(*_WHITE)
        self.set_xy(15, 4.5)
        self.cell(w=120, h=8, text="ReOrder  |  Trendyol Retention Raporu")
        self.set_xy(135, 4.5)
        self.cell(w=60, h=8, text=self.store_name, align="R")
        self.set_text_color(0, 0, 0)

    # ── Altbilgi ───────────────────────────────────────────────────────────────
    def footer(self) -> None:
        self.set_xy(self.l_margin, -12)
        self.set_font("Helvetica", style="I", size=8)
        self.set_text_color(*_GRAY)
        self.cell(
            0, 8,
            f"ReOrder  |  Rapor Tarihi: {self.report_date}  |  Sayfa {self.page_no()}",
            align="C",
        )
        self.set_text_color(0, 0, 0)

    # ── Bölüm başlığı ─────────────────────────────────────────────────────────
    def section_title(self, title: str) -> None:
        self.set_x(self.l_margin)
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", style="B", size=10)
        self.cell(0, 7, f"  {_tr(title)}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    # ── KPI kartı ─────────────────────────────────────────────────────────────
    def kpi_box(self, label: str, value: str, x: float, y: float, w: float = 42) -> None:
        h = 16
        self.set_fill_color(*_LIGHT)
        self.rect(x, y, w, h, style="F")
        # Sol turuncu şerit
        self.set_fill_color(*_ORANGE)
        self.rect(x, y, 1.5, h, style="F")
        # Etiket
        self.set_xy(x + 3, y + 1.5)
        self.set_font("Helvetica", size=7)
        self.set_text_color(*_GRAY)
        self.cell(w - 4, 5, _tr(label.upper()))
        # Değer
        self.set_xy(x + 3, y + 7.5)
        self.set_font("Helvetica", style="B", size=11)
        self.set_text_color(*_DARK)
        self.cell(w - 4, 7, str(value))
        self.set_text_color(0, 0, 0)

    # ── Tablo başlığı ─────────────────────────────────────────────────────────
    def table_header(self, columns: list[tuple[str, float]]) -> None:
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", style="B", size=8)
        for label, width in columns:
            self.cell(width, 6, label, fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)

    # ── Tablo satırı ─────────────────────────────────────────────────────────
    def table_row(self, values: list[str], widths: list[float], idx: int) -> None:
        bg = _LIGHT if idx % 2 == 0 else _WHITE
        self.set_fill_color(*bg)
        self.set_font("Helvetica", size=8)
        for v, w in zip(values, widths):
            self.cell(w, 5.5, str(v), fill=True)
        self.ln()


# ─────────────────────────────────────────────────────────────────────────────
# Grafik üreticiler (matplotlib → PNG bytes)
# ─────────────────────────────────────────────────────────────────────────────

def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _chart_trend(trend: pd.DataFrame) -> bytes:
    """Aylık gelir (bar) + sipariş (çizgi) çift eksenli grafik."""
    fig, ax1 = plt.subplots(figsize=(7.2, 2.6))
    ax2 = ax1.twinx()

    x = np.arange(len(trend))
    ax1.bar(x, trend["revenue"], color="#F27A1A", alpha=0.80, label="Gelir")
    ax2.plot(x, trend["orders"], color="#3B82F6", lw=2,
             marker="o", ms=4, label="Siparis")

    ax1.set_xticks(x)
    ax1.set_xticklabels(trend["month_str"].tolist(), rotation=35, ha="right", fontsize=7)
    ax1.set_ylabel("Gelir (TL)", fontsize=8, color="#F27A1A")
    ax2.set_ylabel("Siparis", fontsize=8, color="#3B82F6")
    ax1.tick_params(axis="y", labelcolor="#F27A1A", labelsize=7)
    ax2.tick_params(axis="y", labelcolor="#3B82F6", labelsize=7)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1000:.0f}k" if v >= 1000 else str(int(v))))

    handles = [
        mpatches.Patch(color="#F27A1A", alpha=0.80, label="Gelir (TL)"),
        mpatches.Patch(color="#3B82F6", label="Siparis Sayisi"),
    ]
    ax1.legend(handles=handles, loc="upper left", fontsize=7)
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _chart_segments(seg_df: pd.DataFrame) -> bytes:
    """Segment dağılımı yatay bar grafiği."""
    summary = (
        seg_df.groupby("segment")["customer_identifier"]
        .count()
        .sort_values()
    )
    label_map = {
        "Sadik Musteri":   "#10B981",
        "Gelisen Musteri": "#3B82F6",
        "Yeni Musteri":    "#F59E0B",
        "Risk Altinda":    "#EF4444",
        "Tek Alisveris":   "#9CA3AF",
        "Kaybolma Riski":  "#6B7280",
    }
    labels = [_tr(l) for l in summary.index]
    colors = [label_map.get(l, "#F27A1A") for l in labels]

    fig, ax = plt.subplots(figsize=(5.5, max(1.8, len(labels) * 0.45)))
    bars = ax.barh(labels, summary.values, color=colors)
    ax.set_xlabel("Musteri Sayisi", fontsize=8)
    ax.tick_params(labelsize=8)
    for bar, val in zip(bars, summary.values):
        ax.text(val + 0.2, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_bytes(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Ana üretici fonksiyon
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(user_id: int, store_name: str, store_id: int | None = None) -> bytes:
    """
    Kullanıcı (veya aktif mağaza) için tam analitik PDF raporu üretir.

    Dönüş:
        PDF içeriği bytes olarak (Streamlit st.download_button ile kullanılabilir)
    """
    # ── Veri çek (aktif mağazaya göre filtreli) ─────────────────────────────────
    metrics  = get_summary_metrics(user_id, store_id)
    trend    = get_monthly_trend(user_id, store_id)
    ret_df, cohort_sizes = get_cohort_retention(user_id, store_id)
    seg_df   = get_customer_segments(user_id, store_id)
    top10    = get_top_customers(user_id, n=10, store_id=store_id)

    pdf = _ReOrderPDF(store_name)
    pdf.add_page()
    M = 15  # sol margin

    # ══════════════════════════════════════════════════════════════════════════
    # SAYFA 1 — Özet Metrikler + Trend
    # ══════════════════════════════════════════════════════════════════════════

    # Tarih satırı
    pdf.set_x(M)
    pdf.set_font("Helvetica", style="I", size=9)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 6, f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y  %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    # KPI — Satır 1
    pdf.section_title("Ozet Metrikler")
    W, GAP = 42, 2
    y0 = pdf.get_y()
    pdf.kpi_box("Toplam Siparis",       f"{metrics['total_orders']:,}",                M,              y0, W)
    pdf.kpi_box("Benzersiz Musteri",    f"{metrics['unique_customers']:,}",             M + W + GAP,   y0, W)
    pdf.kpi_box("Toplam Gelir",         f"TL{metrics['total_revenue']:,.0f}",           M + 2*(W+GAP), y0, W)
    pdf.kpi_box("Ort. Siparis Degeri",  f"TL{metrics['avg_order_value']:,.0f}",         M + 3*(W+GAP), y0, W)

    # KPI — Satır 2
    y1 = y0 + 20
    pdf.kpi_box("Tekrar Orani",         f"%{metrics['repeat_rate']}",                  M,              y1, W)
    pdf.kpi_box("Ortalama LTV",         f"TL{metrics['avg_ltv']:,.0f}",                M + W + GAP,   y1, W)
    pdf.kpi_box("Tekrar Eden Musteri",  f"{metrics['repeat_customers']:,}",             M + 2*(W+GAP), y1, W)

    pdf.set_xy(M, y1 + 20)
    pdf.ln(2)

    # Aylık trend grafiği
    if not trend.empty:
        pdf.section_title("Aylik Gelir & Siparis Trendi")
        chart_img = _chart_trend(trend)
        pdf.image(io.BytesIO(chart_img), x=M, w=180, h=58)
        pdf.ln(3)

    # Aylık özet tablosu
    if not trend.empty:
        pdf.section_title("Aylik Ozet Tablosu")
        cols = [("Ay", 36), ("Siparis", 30), ("Gelir (TL)", 54), ("Musteri", 30)]
        widths = [c[1] for c in cols]
        pdf.table_header(cols)
        for i, (_, row) in enumerate(trend.sort_values("month_str", ascending=False).head(12).iterrows()):
            pdf.table_row(
                [row["month_str"], str(int(row["orders"])),
                 f"TL{row['revenue']:,.0f}", str(int(row["unique_customers"]))],
                widths, i,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # SAYFA 2 — Cohort Retention Matrisi
    # ══════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("Cohort Retention Matrisi")

    pdf.set_font("Helvetica", style="I", size=8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(180, 5,
        "Her satir o ay ilk kez alisveris yapan musterileri gosterir. "
        "Yuzde degerleri o cohort'tan geri donen musteri oranini gosterir."
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    if not ret_df.empty:
        show_cols = [c for c in ret_df.columns if isinstance(c, int) and c <= 8]
        matrix = ret_df[show_cols].copy()

        cohort_w = 28
        size_w   = 14
        cell_w   = int((180 - cohort_w - size_w) / max(len(show_cols), 1))

        # Tablo başlığı
        pdf.set_fill_color(*_DARK)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", style="B", size=7)
        pdf.cell(cohort_w, 6, "Cohort Ayi", fill=True)
        pdf.cell(size_w,   6, "n",          fill=True, align="C")
        for c in show_cols:
            pdf.cell(cell_w, 6, f"Ay {c}", fill=True, align="C")
        pdf.ln()

        for row_i, (cohort, row) in enumerate(matrix.iterrows()):
            size = int(cohort_sizes.get(cohort, 0))
            bg   = _LIGHT if row_i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", size=7)
            pdf.cell(cohort_w, 5.5, str(cohort), fill=True)
            pdf.cell(size_w,   5.5, str(size),   fill=True, align="C")

            for c in show_cols:
                val = row.get(c, np.nan)
                if pd.isna(val) or val == 0:
                    pdf.set_fill_color(*bg)
                    pdf.set_text_color(*_GRAY)
                    display = "-"
                elif val >= 80:
                    pdf.set_fill_color(*_GREEN);  pdf.set_text_color(*_WHITE); display = f"%{val:.0f}"
                elif val >= 50:
                    pdf.set_fill_color(*_YELLOW); pdf.set_text_color(*_DARK);  display = f"%{val:.0f}"
                elif val >= 20:
                    pdf.set_fill_color(249, 115, 22); pdf.set_text_color(*_WHITE); display = f"%{val:.0f}"
                else:
                    pdf.set_fill_color(*_RED);    pdf.set_text_color(*_WHITE); display = f"%{val:.0f}"
                pdf.cell(cell_w, 5.5, display, fill=True, align="C")
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(*bg)
            pdf.ln()

        # Renk açıklaması
        pdf.ln(3)
        pdf.set_font("Helvetica", style="I", size=7)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 5, "Renk: Yesil >= %80  |  Sari >= %50  |  Turuncu >= %20  |  Kirmizi < %20")
        pdf.set_text_color(0, 0, 0)

    # ══════════════════════════════════════════════════════════════════════════
    # SAYFA 3 — Segmentler & Top 10
    # ══════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("Musteri Segmentleri (RFM Analizi)")

    if not seg_df.empty:
        # Segment grafik + tablo yan yana
        chart2_bytes = _chart_segments(seg_df)
        pdf.image(io.BytesIO(chart2_bytes), x=M, y=pdf.get_y(), w=90, h=48)

        # Tablo — sağ taraf
        seg_summary = (
            seg_df.groupby("segment")
            .agg(musteri=("customer_identifier", "count"),
                 gelir=("total_revenue", "sum"))
            .sort_values("musteri", ascending=False)
            .reset_index()
        )
        x_tbl = M + 92
        y_tbl = pdf.get_y()
        pdf.set_xy(x_tbl, y_tbl)

        pdf.set_fill_color(*_DARK)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", style="B", size=7)
        for lbl, w in [("Segment", 44), ("Musteri", 17), ("Gelir (TL)", 24)]:
            pdf.cell(w, 6, lbl, fill=True)
        pdf.ln()

        for i, row in seg_summary.iterrows():
            pdf.set_xy(x_tbl, pdf.get_y())
            bg = _LIGHT if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", size=7)
            pdf.cell(44, 5.5, _tr(str(row["segment"])), fill=True)
            pdf.cell(17, 5.5, str(int(row["musteri"])), fill=True, align="C")
            pdf.cell(24, 5.5, f"TL{row['gelir']:,.0f}", fill=True, align="R")
            pdf.ln()

        pdf.set_xy(M, y_tbl + 52)
        pdf.ln(4)

    # Top 10 Müşteri tablosu
    if not top10.empty:
        pdf.section_title("En Yuksek LTV — Top 10 Musteri")
        cols2 = [("#", 12), ("Musteri Adi", 110), ("LTV (TL)", 38)]
        widths2 = [c[1] for c in cols2]
        pdf.table_header(cols2)
        for i, row in top10.iterrows():
            pdf.table_row(
                [str(i + 1), _tr(str(row["musteri"])[:45]), f"TL{row['ltv']:,.2f}"],
                widths2, i,
            )

    return bytes(pdf.output())
