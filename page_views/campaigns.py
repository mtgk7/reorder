"""pages/campaigns.py — E-posta Kampanyaları sayfası"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime

from src.analytics import get_summary_metrics, get_customer_segments
from src.email_service import (
    save_smtp_settings, load_smtp_settings,
    send_test_email, send_campaign_report,
    save_campaign_log, load_campaign_history,
    build_template, SEGMENT_TEMPLATES, SMTPConfig,
)
from src.ui_helpers import _section, _header, _plan_gate


def run() -> None:
    if not _plan_gate("campaigns"):
        return
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("📧", "E-posta Kampanyaları", "Segment bazlı müşteri iletişimi")

    tab_smtp, tab_send, tab_history = st.tabs([
        "⚙️ SMTP Ayarları", "🚀 Kampanya Gönder", "📋 Geçmiş"
    ])

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
                # Test e-postası her zaman hesabın kayıtlı e-postasına gider —
                # SMTP ayarları başka adres olarak girilse de keyfi adrese gönderim engellenir.
                to_addr = user["email"]
                with st.spinner("Test e-postası gönderiliyor…"):
                    result = send_test_email(cfg, to_addr)
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.error(result["message"])

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

        _section("💬 WhatsApp Şablonu")
        wa_msg = tmpl_c["whatsapp"].replace("{magaza_adi}", user["store_name"])
        st.code(wa_msg, language=None)
        st.caption("Kopyalayıp Trendyol Sohbet veya WhatsApp Business'tan gönderebilirsiniz.")

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

        _section("📨 E-posta Raporu Gönder")
        # Kampanya raporu her zaman hesabın kayıtlı e-postasına gider — keyfi
        # adrese gönderim için serbest metin alanı kasıtlı olarak yok.
        recipient = user["email"]
        st.markdown(
            f"""<div class="info-box">ℹ️ Kampanya raporu hesabınızın kayıtlı e-postasına
            (<b>{recipient}</b>) gönderilir. Raporda müşteri listesi ve kişiselleştirilmiş
            mesaj şablonu yer alır. Müşterilere Trendyol mesajlaşma veya WhatsApp üzerinden
            ulaşabilirsiniz.</div>""",
            unsafe_allow_html=True,
        )

        send_btn = st.button("🚀 Kampanya Raporu Gönder", type="primary", use_container_width=True)
        if send_btn:
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
