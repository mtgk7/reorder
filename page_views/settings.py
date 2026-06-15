"""pages/settings.py — Ayarlar sayfası"""
from __future__ import annotations
import streamlit as st

from src.auth import update_store_name, change_password
from src.trendyol_api import save_credentials, load_credentials, TrendyolClient
from src.database import (
    save_goals, load_goals,
    get_or_create_referral_code, use_referral_code, get_referral_stats,
    get_weekly_report_settings, save_weekly_report_settings, mark_weekly_report_sent,
)
from src.email_service import load_smtp_settings
from src.analytics import get_period_comparison
from src.ui_helpers import _section, _header, _plan_gate, _PLAN_BADGE_COLOR, _PLAN_UPGRADE, _PLAN_PRICES


def run() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    _header("⚙️", "Ayarlar", "Hesap ve mağaza bilgilerinizi yönetin")

    tab_account, tab_goals, tab_api, tab_plan, tab_weekly, tab_referral = st.tabs([
        "👤 Hesap Bilgileri", "🎯 Hedefler", "🔌 Trendyol API (Enterprise)",
        "💎 Plan Yönetimi", "📅 Haftalık Rapor", "🎁 Referral",
    ])

    with tab_goals:
        _section("🎯 Aylık Hedefler")
        st.markdown(
            """<div class="info-box">Hedeflerinizi belirleyin — Dashboard'da ilerlemenizi progress bar olarak görün.</div>""",
            unsafe_allow_html=True,
        )
        cur_goals = load_goals(user["id"], store_id)
        with st.form("goals_form"):
            g1, g2, g3 = st.columns(3)
            gelir_h   = g1.number_input("💰 Aylık Gelir Hedefi (₺)", value=float(cur_goals.get("gelir", 0)), min_value=0.0, step=1000.0)
            musteri_h = g2.number_input("👤 Yeni Müşteri Hedefi", value=float(cur_goals.get("musterí", 0)), min_value=0.0, step=5.0)
            ret_h     = g3.number_input("🔄 Retention Oranı Hedefi (%)", value=float(cur_goals.get("retention", 0)), min_value=0.0, max_value=100.0, step=1.0)
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
            old_pw  = st.text_input("Mevcut Şifre", type="password")
            new_pw  = st.text_input("Yeni Şifre", type="password")
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

    with tab_plan:
        _cur_plan   = user.get("plan", "Starter")
        _cur_period = user.get("plan_period", "m")
        _badge_col2 = _PLAN_BADGE_COLOR.get(_cur_plan, "#6B7280")
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:12px;margin-bottom:1rem;">
            <span style="font-size:1.4rem;font-weight:700;">Mevcut Planınız:</span>
            <span style="background:{_badge_col2};color:#fff;padding:6px 18px;border-radius:999px;font-weight:700;font-size:1rem;letter-spacing:.06em;">
                {_cur_plan.upper()}
            </span>
            <span style="color:#9CA3AF;font-size:.85rem;">{'Yıllık' if _cur_period == 'y' else 'Aylık'} ödeme</span>
            </div>""",
            unsafe_allow_html=True,
        )
        _upgrade_plan = _PLAN_UPGRADE.get(_cur_plan)
        if _upgrade_plan:
            st.markdown(f"**{_upgrade_plan}** planına yükselterek daha fazla özelliğe erişin.")
            if st.button(f"⬆️ {_upgrade_plan} Planına Geç", use_container_width=True, type="primary"):
                _up_price, _up_unit = _PLAN_PRICES.get(_cur_period, _PLAN_PRICES["m"]).get(_upgrade_plan, (0, "/ay"))
                st.session_state.selected_plan = {
                    "name": _upgrade_plan,
                    "price": _up_price,
                    "unit": _up_unit,
                    "period": _cur_period,
                }
                st.session_state.new_user = True
                st.rerun()
        else:
            st.success("En yüksek planda bulunuyorsunuz. Tüm özellikler açık!")

    with tab_api:
        if _plan_gate("trendyol_api"):
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
                    st.session_state.pop(f"_ty_creds_{user['id']}_{store_id}", None)
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

    with tab_weekly:
        if _plan_gate("weekly_report"):
            _header_weekly = get_weekly_report_settings(user["id"])
            _smtp_cfg = load_smtp_settings(user["id"])

            _section("📅 Haftalık Özet Raporu")
            st.markdown(
                """<div class="info-box">
                Her Pazartesi sabahı mağazanızın haftalık özetini e-posta olarak alın.
                Gelir, sipariş, yeni müşteri ve retention metriklerini içerir.
                <br><br>📧 Rapor SMTP ayarlarınızla gönderilir. Önce <b>E-posta Kampanyaları → SMTP Ayarları</b>
                sekmesini yapılandırın.
                </div>""",
                unsafe_allow_html=True,
            )

            if not _smtp_cfg:
                st.warning("⚠️ Haftalık rapor için önce SMTP yapılandırması gereklidir.")
            else:
                _wr_enabled = st.toggle(
                    "Haftalık raporu etkinleştir",
                    value=_header_weekly["enabled"],
                    key="wr_toggle",
                )
                if _wr_enabled != _header_weekly["enabled"]:
                    save_weekly_report_settings(user["id"], _wr_enabled)
                    st.success("✅ Ayar kaydedildi!")
                    st.rerun()

                if _header_weekly["last_sent"]:
                    st.caption(f"Son gönderim: {_header_weekly['last_sent']}")

                st.markdown("&nbsp;")
                st.markdown("**Test — Şimdi Gönder**")
                if st.button("📧 Test Raporu Gönder", key="wr_test_btn"):
                    try:
                        from src.analytics import get_current_month_metrics as _gmm, get_top_customers as _gtc
                        from src.email_service import send_weekly_summary
                        _metrics = _gmm(user["id"], store_id)
                        _cmp_data = get_period_comparison(user["id"], store_id, "month")
                        _top = _gtc(user["id"], n=5, store_id=store_id)
                        _top_list = [{"musteri": r["musteri"], "ltv": r["ltv"]} for _, r in _top.iterrows()] if not _top.empty else []
                        stores = st.session_state.get("stores", [])
                        store_name_wr = next((s["store_name"] for s in stores if s["id"] == store_id), user["store_name"])
                        with st.spinner("Gönderiliyor…"):
                            res = send_weekly_summary(
                                _smtp_cfg, user["email"], store_name_wr,
                                _metrics, _cmp_data, _top_list,
                            )
                        if res["success"]:
                            st.success(res["message"])
                            mark_weekly_report_sent(user["id"])
                        else:
                            st.error(res["message"])
                    except Exception as e:
                        st.error(f"Hata: {e}")

    with tab_referral:
        _section("🎁 Arkadaşını Davet Et — Kazan!")
        st.markdown(
            """<div class="info-box">
            Arkadaşlarınızı ReOrder'a davet edin. Her başarılı davet için
            <b>siz +30 gün</b>, arkadaşınız da <b>+30 gün</b> ücretsiz kullanım kazanır!
            </div>""",
            unsafe_allow_html=True,
        )

        try:
            referral_code = get_or_create_referral_code(user["id"])
            stats = get_referral_stats(user["id"])

            app_url = "https://reorder-81nz.onrender.com"
            ref_url = f"{app_url}/?ref={referral_code}"

            r1, r2, r3 = st.columns(3)
            r1.markdown(
                f"""<div class="kpi-card"><div class="kpi-label">REFERRAL KODUNUZ</div>
                <div class="kpi-value" style="font-size:1.4rem;letter-spacing:.1em;">{referral_code}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            r2.markdown(
                f"""<div class="kpi-card"><div class="kpi-label">DAVET EDİLEN</div>
                <div class="kpi-value">{stats['total_referrals']}</div>
                <div class="kpi-sub">kişi kaydoldu</div></div>""",
                unsafe_allow_html=True,
            )
            r3.markdown(
                f"""<div class="kpi-card"><div class="kpi-label">KAZANILAN BONUS</div>
                <div class="kpi-value">{stats['bonus_days']} gün</div>
                <div class="kpi-sub">ücretsiz kullanım</div></div>""",
                unsafe_allow_html=True,
            )

            st.markdown("&nbsp;")
            _section("Davet Linki")
            st.code(ref_url)
            st.caption("Linki kopyalayıp arkadaşlarınızla paylaşın.")

            st.markdown("&nbsp;")
            _section("Referral Kodu Kullan")
            with st.form("use_referral_form"):
                friend_code = st.text_input("Arkadaşınızın referral kodu", placeholder="RO-XXXXXX")
                use_btn = st.form_submit_button("🎁 Kodu Kullan", use_container_width=True)
            if use_btn:
                if not friend_code.strip():
                    st.error("Kod girin.")
                else:
                    res_ref = use_referral_code(friend_code.strip(), user["id"])
                    if res_ref["success"]:
                        st.success(f"✅ {res_ref['bonus_days']} gün bonus kazandınız! Kodu paylaşan arkadaşınız da kazandı.")
                        st.balloons()
                    else:
                        st.error(res_ref.get("error", "Kod kullanılamadı."))
        except Exception as e:
            st.error(f"Referral sistemi yüklenemedi: {e}")
