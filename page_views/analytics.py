"""pages/analytics.py — Analitik sayfası"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

from src.analytics import (
    get_summary_metrics, get_cohort_retention, get_monthly_trend,
    get_new_vs_returning, get_ltv_distribution, get_top_customers,
    get_product_analysis, get_revenue_forecast, get_cross_sell_matrix,
)
from src.ui_helpers import _fmt_tl, _header, _section, _plan_limits


def run() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("📈", "Analitik", "Cohort (Müşteri Grubu) Retention, LTV ve Müşteri Davranışı")

    m = get_summary_metrics(user["id"], store_id)
    if not m["has_data"]:
        st.info("Veri bulunamadı. Lütfen önce sipariş yükleyin.")
        return

    _analytics_tabs_allowed = _plan_limits()["analytics_tabs"]
    _all_tab_defs = [
        ("cohort",    "🔢 Cohort Analizi"),
        ("ltv",       "💰 LTV Analizi"),
        ("retention", "📉 Retention Trendi"),
        ("product",   "📦 Ürün Analizi"),
        ("forecast",  "🔮 Gelir Tahmini"),
        ("crosssell", "🔗 Cross-Sell"),
    ]
    _visible_defs = [(k, lbl) for k, lbl in _all_tab_defs if k in _analytics_tabs_allowed]
    _created_tabs = st.tabs([lbl for _, lbl in _visible_defs])
    _tab_map = {k: tab for (k, _), tab in zip(_visible_defs, _created_tabs)}
    tab_cohort = _tab_map.get("cohort")

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
            show_cols = [c for c in ret_df.columns if c <= 11]
            display = ret_df[show_cols].copy()
            z = display.values.tolist()
            x_labels = [f"Ay {int(c)}" for c in show_cols]
            y_labels = [str(p) for p in display.index]
            text_labels = [
                [f"{v:.0f}%" if v > 0 else "" for v in row]
                for row in display.values
            ]
            fig = go.Figure(go.Heatmap(
                z=z, x=x_labels, y=y_labels,
                text=text_labels, texttemplate="%{text}",
                textfont={"size": 11},
                colorscale="RdYlGn", zmin=0, zmax=100,
                colorbar=dict(title="Retention %"),
            ))
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
                sizes_df, x="Cohort (Müş. Grubu) Ayı", y="Müşteri Sayısı",
                color_discrete_sequence=["#F27A1A"], template="plotly_white",
            )
            fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    if "ltv" in _tab_map:
        with _tab_map["ltv"]:
            ltv_df = get_ltv_distribution(user["id"], store_id)
            top10 = get_top_customers(user["id"], store_id=store_id)

            if ltv_df.empty:
                st.info("LTV verisi yok.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    _section("LTV Dağılımı (Histogram)")
                    fig = px.histogram(
                        ltv_df, x="ltv", nbins=30,
                        labels={"ltv": "Müşteri LTV (₺)"},
                        color_discrete_sequence=["#F27A1A"], template="plotly_white",
                    )
                    fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Müşteri Sayısı")
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    _section("En İyi 10 Müşteri")
                    if not top10.empty:
                        fig2 = px.bar(
                            top10.head(10), x="ltv", y="musteri", orientation="h",
                            labels={"ltv": "LTV (₺)", "musteri": ""},
                            color_discrete_sequence=["#3B82F6"], template="plotly_white",
                        )
                        fig2.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
                        st.plotly_chart(fig2, use_container_width=True)

                _section("Pareto Analizi (80/20 Kuralı)")
                ltv_sorted = ltv_df.sort_values("ltv", ascending=False).reset_index(drop=True)
                total_rev = ltv_sorted["ltv"].sum()
                ltv_sorted["cumulative_pct"] = ltv_sorted["ltv"].cumsum() / total_rev * 100
                ltv_sorted["customer_pct"] = (ltv_sorted.index + 1) / len(ltv_sorted) * 100
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(
                    x=ltv_sorted["customer_pct"], y=ltv_sorted["cumulative_pct"],
                    fill="tozeroy", line=dict(color="#F27A1A", width=2), name="Kümülatif Gelir",
                ))
                fig3.add_hline(y=80, line_dash="dash", line_color="#6B7280", annotation_text="80%")
                fig3.update_layout(
                    height=260, margin=dict(l=0, r=0, t=10, b=0),
                    xaxis_title="Müşteri % (LTV'ye göre sıralı)",
                    yaxis_title="Kümülatif Gelir %", template="plotly_white",
                )
                st.plotly_chart(fig3, use_container_width=True)

    if "retention" in _tab_map:
        with _tab_map["retention"]:
            _section("Aylık Retention Oranı Trendi")
            nvr = get_new_vs_returning(user["id"], store_id)
            trend = get_monthly_trend(user["id"], store_id)
            if nvr.empty or trend.empty:
                st.info("Yeterli veri yok.")
            else:
                merged = nvr.merge(trend[["month_str", "orders"]], on="month_str", how="left")
                if "yeni_musteri" in merged.columns and "geri_donen" in merged.columns:
                    merged["total_customers"] = merged.get("yeni_musteri", 0) + merged.get("geri_donen", 0)
                    merged["retention_rate"] = (
                        merged.get("geri_donen", 0) / merged["total_customers"].replace(0, np.nan) * 100
                    ).round(1)
                    fig = px.line(
                        merged, x="month_str", y="retention_rate", markers=True,
                        labels={"month_str": "Ay", "retention_rate": "Retention Oranı (%)"},
                        color_discrete_sequence=["#10B981"], template="plotly_white",
                    )
                    fig.update_traces(line=dict(width=2.5))
                    fig.update_layout(
                        height=300, margin=dict(l=0, r=0, t=10, b=0),
                        yaxis=dict(range=[0, 100], ticksuffix="%"),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    _section("Aylık Sipariş Hacmi")
                    fig2 = px.bar(
                        trend, x="month_str", y="orders",
                        labels={"month_str": "Ay", "orders": "Sipariş Sayısı"},
                        color_discrete_sequence=["#F27A1A"], template="plotly_white",
                    )
                    fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig2, use_container_width=True)

    if "product" in _tab_map:
        with _tab_map["product"]:
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
                        x=ret_df["retention_rate"], y=ret_df["product_label"], orientation="h",
                        marker=dict(color=ret_df["retention_rate"], colorscale=[[0, "#FEE2E2"], [0.5, "#F27A1A"], [1, "#10B981"]], showscale=False),
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
                    ltv_df2 = prod["ltv"].copy()
                    ltv_df2["product_label"] = ltv_df2["product_name"].apply(
                        lambda x: x[:32] + "…" if len(str(x)) > 32 else x
                    )
                    fig_ltv2 = go.Figure(go.Bar(
                        x=ltv_df2["avg_revenue_per_buyer"], y=ltv_df2["product_label"], orientation="h",
                        marker=dict(color="#3B82F6"),
                        text=ltv_df2["avg_revenue_per_buyer"].apply(lambda v: f"₺{v:,.0f}"),
                        textposition="outside",
                        hovertemplate="<b>%{y}</b><br>Ort. Gelir: ₺%{x:,.2f}<extra></extra>",
                    ))
                    fig_ltv2.update_layout(
                        height=max(280, len(ltv_df2) * 30 + 60),
                        margin=dict(l=0, r=70, t=8, b=0),
                        xaxis=dict(title="Müşteri Başı Gelir (₺)", tickprefix="₺"),
                        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                        template="plotly_white",
                    )
                    st.plotly_chart(fig_ltv2, use_container_width=True)
                _section("📋 Ürün Detay Tablosu")
                tbl = ret_df[["product_name", "buyer_count", "repeat_buyers", "retention_rate", "total_revenue"]].copy()
                tbl.columns = ["Ürün", "Alıcı", "Tekrar Alıcı", "Tekrar Oranı (%)", "Toplam Gelir (₺)"]
                tbl["Toplam Gelir (₺)"] = tbl["Toplam Gelir (₺)"].apply(_fmt_tl)
                st.dataframe(tbl, use_container_width=True, hide_index=True)

    if "forecast" in _tab_map:
        with _tab_map["forecast"]:
            _section("🔮 Gelir Tahmini — Lineer Trend Analizi")
            st.markdown(
                """<div class="info-box" style="font-size:.82rem;">
                Geçmiş aylık gelir verisiyle ağırlıklı lineer regresyon kullanılarak gelir tahmini yapılır.
                Yakın dönem aylar daha yüksek ağırlık alır.
                </div>""",
                unsafe_allow_html=True,
            )
            fc_horizon = st.slider("Kaç günlük tahmin?", 30, 180, 90, step=30, key="fc_horizon")
            fc = get_revenue_forecast(user["id"], store_id, horizon_days=fc_horizon)

            if fc["history"].empty:
                st.info("Tahmin için yeterli veri yok.")
            else:
                trend_color = "#10B981" if fc["trend"] == "artış" else ("#EF4444" if fc["trend"] == "düşüş" else "#6B7280")
                trend_icon  = "📈" if fc["trend"] == "artış" else ("📉" if fc["trend"] == "düşüş" else "➡️")
                fc1, fc2, fc3 = st.columns(3)
                fc1.markdown(
                    f"""<div class="kpi-card"><div class="kpi-label">TREND</div>
                    <div class="kpi-value" style="color:{trend_color};">{trend_icon} {fc['trend'].title()}</div></div>""",
                    unsafe_allow_html=True,
                )
                fc2.markdown(
                    f"""<div class="kpi-card"><div class="kpi-label">AYLIK BÜYÜME</div>
                    <div class="kpi-value">%{fc['monthly_growth']:+.1f}</div>
                    <div class="kpi-sub">son 3 ay vs önceki 3 ay</div></div>""",
                    unsafe_allow_html=True,
                )
                fc_total = float(fc["forecast"]["revenue"].sum()) if not fc["forecast"].empty else 0
                fc3.markdown(
                    f"""<div class="kpi-card"><div class="kpi-label">{fc_horizon} GÜNLÜK TAHMİN</div>
                    <div class="kpi-value">{_fmt_tl(fc_total)}</div>
                    <div class="kpi-sub">tahmini toplam gelir</div></div>""",
                    unsafe_allow_html=True,
                )
                st.markdown("&nbsp;")
                _section("Tarihsel Gelir + Tahmin")
                fig_fc = go.Figure()
                hist = fc["history"]
                fig_fc.add_trace(go.Bar(x=hist["month_str"], y=hist["revenue"], name="Gerçek Gelir", marker_color="#F27A1A", opacity=0.85))
                if not fc["forecast"].empty:
                    fdf = fc["forecast"]
                    fig_fc.add_trace(go.Scatter(x=fdf["date_str"], y=fdf["upper"], mode="lines", line=dict(width=0), showlegend=False, name="Üst Sınır"))
                    fig_fc.add_trace(go.Scatter(x=fdf["date_str"], y=fdf["lower"], fill="tonexty", mode="lines", line=dict(width=0), fillcolor="rgba(59,130,246,0.12)", name="Güven Aralığı"))
                    fig_fc.add_trace(go.Scatter(x=fdf["date_str"], y=fdf["revenue"], mode="lines", line=dict(color="#3B82F6", width=2.5, dash="dash"), name="Tahmin (günlük)"))
                fig_fc.update_layout(
                    height=360, margin=dict(l=0, r=0, t=10, b=0),
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1),
                    xaxis_title="", yaxis_title="Gelir (₺)",
                    yaxis=dict(tickprefix="₺", tickformat=",.0f"),
                )
                st.plotly_chart(fig_fc, use_container_width=True)

    if "crosssell" in _tab_map:
        with _tab_map["crosssell"]:
            _section("🔗 Ürün Öneri Matrisi — Cross-Sell Analizi")
            st.markdown(
                """<div class="info-box" style="font-size:.82rem;">
                Aynı müşteri tarafından birlikte satın alınan ürün çiftleri.
                <b>Güven (A→B)</b>: A ürününü alanların kaçı B'yi de aldı?
                <b>Lift</b>: Birliktelik ne kadar anlamlı?
                </div>""",
                unsafe_allow_html=True,
            )
            cs_df = get_cross_sell_matrix(user["id"], store_id)
            if cs_df.empty:
                st.info("Cross-sell analizi için yeterli ürün verisi yok. En az 3 müşteri 2+ farklı ürün almalı.")
            else:
                _section(f"En Güçlü {min(10, len(cs_df))} Ürün Çifti")
                cs_top = cs_df.head(10).copy()
                cs_top["pair_label"] = cs_top["product_a"].str[:22] + " ↔ " + cs_top["product_b"].str[:22]
                fig_cs = go.Figure(go.Bar(
                    x=cs_top["co_buyers"], y=cs_top["pair_label"], orientation="h",
                    marker=dict(color=cs_top["lift"], colorscale="Oranges", showscale=True, colorbar=dict(title="Lift")),
                    text=cs_top["co_buyers"].apply(lambda v: f"{v} müşteri"),
                    textposition="outside",
                    customdata=cs_top[["confidence_ab", "confidence_ba", "lift"]].values,
                    hovertemplate="<b>%{y}</b><br>Ortak Alıcı: %{x}<br>Güven A→B: %{customdata[0]}%<br>Güven B→A: %{customdata[1]}%<br>Lift: %{customdata[2]}<extra></extra>",
                ))
                fig_cs.update_layout(
                    height=max(280, len(cs_top) * 40 + 60),
                    margin=dict(l=0, r=60, t=8, b=0),
                    xaxis=dict(title="Ortak Alıcı Sayısı"),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    template="plotly_white",
                )
                st.plotly_chart(fig_cs, use_container_width=True)

                _section("📋 Tüm Çiftler Tablosu")
                tbl_cs = cs_df[["product_a", "product_b", "co_buyers", "confidence_ab", "confidence_ba", "lift"]].copy()
                tbl_cs.columns = ["Ürün A", "Ürün B", "Ortak Alıcı", "Güven A→B (%)", "Güven B→A (%)", "Lift"]
                st.dataframe(tbl_cs, use_container_width=True, hide_index=True)
