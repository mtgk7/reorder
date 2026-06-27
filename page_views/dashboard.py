"""pages/dashboard.py — Genel Bakış sayfası"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from src.analytics import (
    get_summary_metrics, get_monthly_trend, get_new_vs_returning,
    get_order_status_kpis, get_top_products, get_daily_revenue,
    get_current_month_metrics, get_anomalies, get_period_comparison,
)
from src.database import load_goals
from src.ui_helpers import _fmt_tl, _kpi, _header, _section, _go, _plan_gate


def run() -> None:
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

    # ── Anlık Bildirimler ──────────────────────────────────────────────────────
    try:
        alerts = get_anomalies(user["id"], store_id)
        if alerts:
            for alert in alerts:
                if alert["severity"] == "high":
                    st.markdown(
                        f"""<div style="background:#FEF2F2;border:1px solid #FECACA;border-left:4px solid #EF4444;
                        border-radius:8px;padding:.8rem 1rem;margin-bottom:.5rem;display:flex;align-items:center;gap:.6rem;">
                        <span style="font-size:1.2rem;">{alert['icon']}</span>
                        <div><b style="color:#991B1B;">{alert['title']}</b>
                        <span style="color:#7F1D1D;font-size:.86rem;"> — {alert['message']}</span></div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-left:4px solid #10B981;
                        border-radius:8px;padding:.8rem 1rem;margin-bottom:.5rem;display:flex;align-items:center;gap:.6rem;">
                        <span style="font-size:1.2rem;">{alert['icon']}</span>
                        <div><b style="color:#065F46;">{alert['title']}</b>
                        <span style="color:#064E3B;font-size:.86rem;"> — {alert['message']}</span></div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
    except Exception:
        pass

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

    st.markdown("""
    <style>
    .mini-dash-divider {
        border: none;
        border-top: 1px solid rgba(242,122,26,.18);
        margin: 1.6rem 0 1rem 0;
    }
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

    kpis = get_order_status_kpis(user["id"], store_id)

    k1, k2, k3 = st.columns(3)
    with k1:
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

    chart_col1, chart_col2 = st.columns(2, gap="medium")

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
                xaxis=dict(title="Toplam Satış Adedi", showgrid=True, gridcolor="#F3F4F6", zeroline=False),
                yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                template="plotly_white",
                plot_bgcolor="#FAFAFA",
                paper_bgcolor="white",
            )
            st.plotly_chart(fig_prod, use_container_width=True)

    with chart_col2:
        _section("📅 Günlük Ciro Trendi")
        daily_rev = get_daily_revenue(user["id"], days=30, store_id=store_id)

        if daily_rev.empty:
            st.markdown('<div class="info-box" style="font-size:.84rem;">📅 Günlük ciro verisi oluşturulamadı.</div>', unsafe_allow_html=True)
        else:
            date_range_label = (
                f"{daily_rev['date_str'].iloc[0]} → {daily_rev['date_str'].iloc[-1]}"
                if len(daily_rev) > 1 else daily_rev["date_str"].iloc[0]
            )
            st.markdown(
                f'<div style="font-size:.76rem; color:#9CA3AF; margin:-6px 0 6px 0;">📆 {date_range_label}</div>',
                unsafe_allow_html=True,
            )
            fig_daily = go.Figure()
            fig_daily.add_trace(go.Scatter(
                x=daily_rev["date_str"], y=daily_rev["revenue"],
                mode="lines+markers", name="Günlük Ciro",
                line=dict(color="#F27A1A", width=2.5, shape="spline"),
                marker=dict(size=5, color="#F27A1A", line=dict(width=1.5, color="white")),
                fill="tozeroy", fillcolor="rgba(242,122,26,.10)",
                hovertemplate="<b>%{x}</b><br>Ciro: ₺%{y:,.2f}<br>Sipariş: %{customdata}<extra></extra>",
                customdata=daily_rev["orders"],
            ))
            if len(daily_rev) >= 3:
                roll = daily_rev["revenue"].rolling(window=min(7, len(daily_rev)), min_periods=1).mean()
                fig_daily.add_trace(go.Scatter(
                    x=daily_rev["date_str"], y=roll,
                    mode="lines", name="7G Ort.",
                    line=dict(color="#3B82F6", width=1.5, dash="dot"),
                    hoverinfo="skip",
                ))
            fig_daily.update_layout(
                height=max(260, len(daily_rev) * 8 + 140),
                margin=dict(l=0, r=0, t=8, b=0),
                xaxis=dict(title="", showgrid=False, tickangle=-35, tickfont=dict(size=10)),
                yaxis=dict(title="Ciro (₺)", showgrid=True, gridcolor="#F3F4F6", zeroline=False, tickprefix="₺", tickformat=",.0f"),
                template="plotly_white",
                plot_bgcolor="#FAFAFA", paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
                hovermode="x unified",
            )
            st.plotly_chart(fig_daily, use_container_width=True)

    st.markdown('<hr class="mini-dash-divider">', unsafe_allow_html=True)

    # ── Hedef / KPI Takibi ───────────────────────────────────────────────────────
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
                        <div style="font-size:1.5rem;font-weight:800;color:#1A1A2E;margin-bottom:.5rem;">{unit}{cur_fmt}</div>
                        <div style="background:#F3F4F6;border-radius:999px;height:8px;overflow:hidden;">
                            <div style="width:{pct}%;height:100%;background:{color};border-radius:999px;"></div>
                        </div>
                        <div style="font-size:.75rem;color:#9CA3AF;margin-top:.4rem;">
                            Hedef: {unit}{tgt_fmt} &nbsp;·&nbsp; <b style="color:{color};">{pct}%</b>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("&nbsp;")

    # ── Dönem Karşılaştırması ─────────────────────────────────────────────────
    st.markdown('<hr style="border:none;border-top:1px solid rgba(242,122,26,.18);margin:1.6rem 0 1rem;">', unsafe_allow_html=True)
    _section("📅 Dönem Karşılaştırması")
    try:
        _cmp_mode = st.radio(
            "Karşılaştırma Dönemi",
            ["Bu Ay vs Geçen Ay", "Bu Yıl vs Geçen Yıl"],
            horizontal=True,
            key="cmp_mode_radio",
            label_visibility="collapsed",
        )
        cmp_mode = "month" if "Ay" in _cmp_mode else "year"
        cmp = get_period_comparison(user["id"], store_id, mode=cmp_mode)
        if cmp:
            cur_lbl  = cmp["cur_label"]
            prev_lbl = cmp["prev_label"]
            cc1, cc2, cc3 = st.columns(3)

            def _delta_badge(pct: float) -> str:
                if pct > 0:
                    return f'<span style="color:#10B981;font-weight:700;font-size:.8rem;">▲ %{abs(pct):.1f}</span>'
                elif pct < 0:
                    return f'<span style="color:#EF4444;font-weight:700;font-size:.8rem;">▼ %{abs(pct):.1f}</span>'
                return '<span style="color:#9CA3AF;font-size:.8rem;">— değişim yok</span>'

            with cc1:
                st.markdown(
                    f"""<div class="kpi-card">
                    <div class="kpi-label">💰 GELİR</div>
                    <div class="kpi-value">{_fmt_tl(cmp['current']['revenue'])}</div>
                    <div class="kpi-sub">{cur_lbl} · {_delta_badge(cmp['delta_revenue_pct'])}</div>
                    <div style="font-size:.75rem;color:#9CA3AF;margin-top:.2rem;">{prev_lbl}: {_fmt_tl(cmp['previous']['revenue'])}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with cc2:
                st.markdown(
                    f"""<div class="kpi-card">
                    <div class="kpi-label">🛒 SİPARİŞ</div>
                    <div class="kpi-value">{cmp['current']['orders']:,}</div>
                    <div class="kpi-sub">{cur_lbl} · {_delta_badge(cmp['delta_orders_pct'])}</div>
                    <div style="font-size:.75rem;color:#9CA3AF;margin-top:.2rem;">{prev_lbl}: {cmp['previous']['orders']:,}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with cc3:
                st.markdown(
                    f"""<div class="kpi-card">
                    <div class="kpi-label">👤 MÜŞTERİ</div>
                    <div class="kpi-value">{cmp['current']['unique_customers']:,}</div>
                    <div class="kpi-sub">{cur_lbl} · {_delta_badge(cmp['delta_customers_pct'])}</div>
                    <div style="font-size:.75rem;color:#9CA3AF;margin-top:.2rem;">{prev_lbl}: {cmp['previous']['unique_customers']:,}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

            st.markdown("&nbsp;")

            if not cmp["daily_current"].empty or not cmp["daily_previous"].empty:
                daily_all = pd.concat([cmp["daily_current"], cmp["daily_previous"]], ignore_index=True)
                if not daily_all.empty:
                    fig_cmp = px.line(
                        daily_all, x="gun", y="revenue", color="seri",
                        color_discrete_map={"Bu Dönem": "#F27A1A", "Önceki Dönem": "#9CA3AF"},
                        labels={"gun": "Gün", "revenue": "Gelir (₺)", "seri": ""},
                        template="plotly_white",
                    )
                    fig_cmp.update_layout(
                        height=220, margin=dict(l=0, r=0, t=8, b=0),
                        legend=dict(orientation="h", yanchor="bottom", y=1),
                    )
                    st.plotly_chart(fig_cmp, use_container_width=True)
    except Exception:
        pass

    _section("Aylık Özet Tablosu")
    if not trend.empty:
        display = trend[["month_str", "orders", "revenue", "unique_customers"]].copy()
        display.columns = ["Ay", "Sipariş", "Gelir (₺)", "Benzersiz Müşteri"]
        display["Gelir (₺)"] = display["Gelir (₺)"].apply(_fmt_tl)
        st.dataframe(display.sort_values("Ay", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("&nbsp;")

    # ── Stok Hızı Uyarısı ─────────────────────────────────────────────────────
    try:
        from src.analytics import get_stock_velocity
        velocity_df = get_stock_velocity(user["id"], store_id)
        if not velocity_df.empty:
            _section("⚡ Satış Hızı — Stok Takibi")
            st.markdown(
                """<div class="info-box">Günlük satış hızına göre ürünlerinizi izleyin.
                Stok miktarınızı girerek tükenme tarihini hesaplayın.</div>""",
                unsafe_allow_html=True,
            )
            for _, row in velocity_df.head(8).iterrows():
                cols = st.columns([3, 1, 2])
                cols[0].markdown(
                    f"<small>{str(row['product_name'])[:40]}</small>",
                    unsafe_allow_html=True,
                )
                stok = cols[1].number_input(
                    "",
                    min_value=0,
                    value=0,
                    key=f"stok_{str(row['product_name'])[:20]}",
                    label_visibility="collapsed",
                )
                if stok > 0:
                    gun = stok / row["gunluk_satis"]
                    renk = "🔴" if gun < 7 else "🟡" if gun < 14 else "🟢"
                    cols[2].markdown(f"{renk} **{gun:.0f} gün**")
                else:
                    cols[2].markdown(
                        f"<small style='color:#9ca3af;'>{row['gunluk_satis']:.2f} adet/gün</small>",
                        unsafe_allow_html=True,
                    )
            st.markdown("&nbsp;")
    except Exception:
        pass

    _section("📄 PDF Rapor")
    if not _plan_gate("pdf_report"):
        return
    st.markdown(
        """<div class="info-box">Tüm metrikleri, cohort (müşteri grubu) matrisini ve müşteri segmentlerini
        tek sayfalık PDF raporu olarak indirin. Mağaza raporlaması veya arşivleme için idealdir.</div>""",
        unsafe_allow_html=True,
    )
    if st.button("📄 PDF Raporu Hazırla", key="pdf_generate_btn"):
        with st.spinner("PDF hazırlanıyor…"):
            try:
                from src.report import generate_report
                pdf_bytes = generate_report(user["id"], store_name, store_id)
                st.session_state["pdf_report"] = {
                    "bytes": bytes(pdf_bytes),
                    "store": store_name,
                    "store_id": store_id,
                }
            except Exception as e:
                st.session_state.pop("pdf_report", None)
                st.error(f"PDF oluşturulurken hata: {e}")

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
