"""pages/upload.py — Veri Yükle sayfası"""
from __future__ import annotations
import streamlit as st

from src.parser import parse_trendyol_file, import_to_db, generate_sample_orders
from src.trendyol_api import save_credentials, load_credentials, sync_orders, TrendyolClient
from src.hepsiburada_api import (
    save_credentials as hb_save_credentials,
    load_credentials as hb_load_credentials,
    sync_orders as hb_sync_orders,
    HepsiburadaClient,
)
from src.analytics import get_summary_metrics
from src.database import delete_all_orders
from src.ui_helpers import _section, _header, _go, marketplace_label


def run() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    stores = st.session_state.get("stores", [])
    active_store = next((s for s in stores if s["id"] == store_id), None)
    store_name = active_store["store_name"] if active_store else user["store_name"]
    marketplace = active_store.get("marketplace") if active_store else "trendyol"
    mp_label = marketplace_label(marketplace)
    is_trendyol = marketplace == "trendyol"
    _header("📁", "Veri Yükle", f"{mp_label} sipariş raporunuzu içe aktarın")

    tab_file, tab_api, tab_sample, tab_manage = st.tabs(
        ["📂 Dosya Yükle", "🔌 API Bağlantısı", "🎲 Örnek Veri", "🗑️ Veri Yönetimi"]
    )

    with tab_file:
        st.markdown(
            f"""<div class="info-box">
            <b>Nasıl yapılır?</b><br>
            {mp_label} Satıcı Paneli → <b>Siparişlerim</b> → <b>Excel İndir</b> butonuyla indirdiğiniz
            <code>.xlsx</code> veya <code>.csv</code> dosyasını buraya yükleyin.
            Sistem sütunları otomatik tanır.
            </div>""",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            f"{mp_label} Sipariş Raporu (.xlsx, .csv)",
            type=["xlsx", "xls", "csv"],
            key="file_uploader",
        )

        if uploaded:
            with st.spinner("Dosya analiz ediliyor…"):
                result = parse_trendyol_file(uploaded)

            if not result["success"]:
                for err in result["errors"]:
                    st.error(err)
                st.markdown(
                    f"""<div class="warn-box">
                    <b>İpucu:</b> {mp_label}'dan indirdiğiniz orijinal Excel dosyasını (formatı değiştirmeden) yükleyin.
                    Sütun adları Türkçe veya İngilizce olabilir.
                    </div>""",
                    unsafe_allow_html=True,
                )
                return

            for warn in result["warnings"]:
                st.warning(warn)

            df = result["data"]
            col_map = result["col_map"]

            _section("Tespit Edilen Sütunlar")
            field_labels = {
                "order_number": "Sipariş No",
                "customer_identifier": "Müşteri",
                "order_date": "Tarih",
                "total_amount": "Tutar",
                "product_name": "Ürün",
                "quantity": "Adet",
                "status": "Durum",
            }
            col_info = {field_labels.get(k, k): v for k, v in col_map.items()}
            st.json(col_info)

            _section(f"Ön İzleme ({len(df):,} satır)")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

            if st.button("✅ Veritabanına Aktar", type="primary"):
                with st.spinner("Aktarılıyor…"):
                    imp = import_to_db(df, user["id"], store_id=store_id)
                _skipped_txt = f" ({imp['skipped']:,} tekrar atlandı.)" if imp['skipped'] else ""
                st.markdown(
                    f'<div class="success-box">✅ <b>{imp["inserted"]:,} yeni sipariş</b> aktarıldı.{_skipped_txt}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("📊 Analizlere Git"):
                    _go("dashboard")

    with tab_api:
        if marketplace not in ("trendyol", "hepsiburada"):
            st.markdown(
                f"""<div class="info-box">
                🔌 <b>{mp_label} için otomatik senkronizasyon henüz desteklenmiyor.</b><br>
                Sipariş verilerinizi 📂 <b>Dosya Yükle</b> sekmesinden CSV/Excel raporu olarak yükleyebilirsiniz —
                tüm analizler ({mp_label} dahil her mağaza için) aynı şekilde çalışır.
                </div>""",
                unsafe_allow_html=True,
            )
        elif is_trendyol:
            creds = load_credentials(user["id"], store_id)

            if not creds:
                st.markdown(
                    """<div class="warn-box">
                    🔌 <b>API bağlantısı kurulmamış.</b>
                    Aşağıya Trendyol Satıcı Paneli'nden aldığınız bilgileri girerek bağlantıyı kurun.
                    <br><br>
                    <b>Nasıl alınır?</b> Trendyol Satıcı Paneli →
                    <b>Entegrasyonlar</b> → <b>API Entegrasyonları</b> → API Bilgileri
                    </div>""",
                    unsafe_allow_html=True,
                )

            with st.expander("🔑 API Kimlik Bilgileri" + (" (Kayıtlı ✅)" if creds else ""), expanded=not bool(creds)):
                with st.form("api_creds_form"):
                    seller_id  = st.text_input("Satıcı ID",  value=creds["seller_id"]  if creds else "", placeholder="Örn: 12345")
                    api_key    = st.text_input("API Key",     value=creds["api_key"]    if creds else "", placeholder="Trendyol API Key")
                    api_secret = st.text_input("API Secret",  value=creds["api_secret"] if creds else "", type="password", placeholder="Trendyol API Secret")

                    col_save, col_test = st.columns(2)
                    with col_save:
                        save_btn = st.form_submit_button("💾 Kaydet", use_container_width=True)
                    with col_test:
                        test_btn = st.form_submit_button("🔗 Bağlantıyı Test Et", use_container_width=True)

                if save_btn:
                    if not (seller_id and api_key and api_secret):
                        st.error("Tüm alanları doldurun.")
                    else:
                        save_credentials(user["id"], seller_id, api_key, api_secret, store_id)
                        st.session_state.pop(f"_ty_creds_{user['id']}_{store_id}", None)
                        st.success("✅ API bilgileri kaydedildi!")
                        st.rerun()

                if test_btn:
                    if not (seller_id and api_key and api_secret):
                        st.error("Önce bilgileri girin.")
                    else:
                        with st.spinner("Bağlantı test ediliyor…"):
                            try:
                                client = TrendyolClient(seller_id, api_key, api_secret)
                                ok = client.test_connection()
                            except Exception:
                                ok = False
                        if ok:
                            st.success("✅ Bağlantı başarılı! API bilgileri doğru.")
                        else:
                            st.error("❌ Bağlantı kurulamadı. Bilgilerinizi kontrol edin.")

            if creds:
                st.markdown("---")
                _section("📥 Sipariş Senkronizasyonu")

                if creds["last_sync_at"]:
                    st.markdown(
                        f"""<div class="success-box">
                        ⏱️ Son senkronizasyon: <b>{creds['last_sync_at']}</b>
                        — {creds['last_sync_count']:,} sipariş eklendi
                        </div>""",
                        unsafe_allow_html=True,
                    )

                st.markdown("Trendyol'dan çekilecek tarih aralığını seçin:")

                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    if st.button("Son 7 Gün",  key="sync_7",  use_container_width=True):
                        st.session_state["sync_preset"] = 7
                with col2:
                    if st.button("Son 30 Gün", key="sync_30", use_container_width=True):
                        st.session_state["sync_preset"] = 30
                with col3:
                    if st.button("Son 90 Gün", key="sync_90", use_container_width=True):
                        st.session_state["sync_preset"] = 90

                import datetime as _dt
                preset_days = st.session_state.get("sync_preset", 30)
                default_start = _dt.date.today() - _dt.timedelta(days=preset_days)
                default_end   = _dt.date.today()

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    sync_start = st.date_input("Başlangıç", value=default_start, key="sync_start")
                with col_d2:
                    sync_end   = st.date_input("Bitiş",     value=default_end,   key="sync_end")

                if st.button("🔄 Siparişleri Senkronize Et", type="primary", use_container_width=True):
                    if sync_start > sync_end:
                        st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
                    else:
                        with st.spinner(f"Trendyol'dan siparişler çekiliyor ({sync_start} → {sync_end})…"):
                            result = sync_orders(
                                user["id"],
                                sync_start.strftime("%Y-%m-%d"),
                                sync_end.strftime("%Y-%m-%d"),
                                store_id,
                            )

                        if result["success"]:
                            if result["inserted"] == 0 and result["skipped"] == 0:
                                st.info("Bu tarih aralığında yeni sipariş bulunamadı.")
                            else:
                                st.markdown(
                                    f"""<div class="success-box">
                                    ✅ Senkronizasyon tamamlandı!<br>
                                    <b>{result['inserted']:,} yeni sipariş</b> eklendi.
                                    {f"({result['skipped']:,} tekrar atlandı.)" if result['skipped'] else ""}
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                                if st.button("📊 Dashboard'a Git", key="api_goto_dash"):
                                    _go("dashboard")
                        else:
                            st.error(f"❌ Hata: {result['error']}")

        elif marketplace == "hepsiburada":
            hb_creds = hb_load_credentials(user["id"], store_id)

            if not hb_creds:
                st.markdown(
                    """<div class="warn-box">
                    🔌 <b>API bağlantısı kurulmamış.</b>
                    Aşağıya Hepsiburada Satıcı Paneli'nden aldığınız bilgileri girerek bağlantıyı kurun.
                    <br><br>
                    <b>Nasıl alınır?</b> Hepsiburada Satıcı Paneli →
                    <b>Entegrasyonlar</b> → <b>API Bilgileri</b>
                    </div>""",
                    unsafe_allow_html=True,
                )

            with st.expander("🔑 API Kimlik Bilgileri" + (" (Kayıtlı ✅)" if hb_creds else ""), expanded=not bool(hb_creds)):
                with st.form("hb_api_creds_form"):
                    hb_merchant_id = st.text_input("Merchant ID", value=hb_creds["merchant_id"] if hb_creds else "", placeholder="Örn: 550e8400-e29b-...")
                    hb_username    = st.text_input("Kullanıcı Adı", value=hb_creds["username"] if hb_creds else "", placeholder="Hepsiburada Satıcı Paneli kullanıcı adı")
                    hb_password    = st.text_input("Şifre", value=hb_creds["password"] if hb_creds else "", type="password", placeholder="Hepsiburada Satıcı Paneli şifresi")

                    col_save, col_test = st.columns(2)
                    with col_save:
                        hb_save_btn = st.form_submit_button("💾 Kaydet", use_container_width=True)
                    with col_test:
                        hb_test_btn = st.form_submit_button("🔗 Bağlantıyı Test Et", use_container_width=True)

                if hb_save_btn:
                    if not (hb_merchant_id and hb_username and hb_password):
                        st.error("Tüm alanları doldurun.")
                    else:
                        hb_save_credentials(user["id"], hb_merchant_id, hb_username, hb_password, store_id)
                        st.session_state.pop(f"_hb_creds_{user['id']}_{store_id}", None)
                        st.success("✅ API bilgileri kaydedildi!")
                        st.rerun()

                if hb_test_btn:
                    if not (hb_merchant_id and hb_username and hb_password):
                        st.error("Önce bilgileri girin.")
                    else:
                        with st.spinner("Bağlantı test ediliyor…"):
                            try:
                                client = HepsiburadaClient(hb_merchant_id, hb_username, hb_password)
                                ok = client.test_connection()
                            except Exception:
                                ok = False
                        if ok:
                            st.success("✅ Bağlantı başarılı! API bilgileri doğru.")
                        else:
                            st.error("❌ Bağlantı kurulamadı. Bilgilerinizi kontrol edin.")

            if hb_creds:
                st.markdown("---")
                _section("📥 Sipariş Senkronizasyonu")

                if hb_creds["last_sync_at"]:
                    st.markdown(
                        f"""<div class="success-box">
                        ⏱️ Son senkronizasyon: <b>{hb_creds['last_sync_at']}</b>
                        — {hb_creds['last_sync_count']:,} sipariş eklendi
                        </div>""",
                        unsafe_allow_html=True,
                    )

                st.markdown("Hepsiburada'dan çekilecek tarih aralığını seçin:")

                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    if st.button("Son 7 Gün",  key="hb_sync_7",  use_container_width=True):
                        st.session_state["hb_sync_preset"] = 7
                with col2:
                    if st.button("Son 30 Gün", key="hb_sync_30", use_container_width=True):
                        st.session_state["hb_sync_preset"] = 30
                with col3:
                    if st.button("Son 90 Gün", key="hb_sync_90", use_container_width=True):
                        st.session_state["hb_sync_preset"] = 90

                import datetime as _dt
                hb_preset_days = st.session_state.get("hb_sync_preset", 30)
                hb_default_start = _dt.date.today() - _dt.timedelta(days=hb_preset_days)
                hb_default_end   = _dt.date.today()

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    hb_sync_start = st.date_input("Başlangıç", value=hb_default_start, key="hb_sync_start")
                with col_d2:
                    hb_sync_end   = st.date_input("Bitiş",     value=hb_default_end,   key="hb_sync_end")

                if st.button("🔄 Siparişleri Senkronize Et", type="primary", use_container_width=True, key="hb_sync_btn"):
                    if hb_sync_start > hb_sync_end:
                        st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
                    else:
                        with st.spinner(f"Hepsiburada'dan siparişler çekiliyor ({hb_sync_start} → {hb_sync_end})…"):
                            hb_result = hb_sync_orders(
                                user["id"],
                                hb_sync_start.strftime("%Y-%m-%d"),
                                hb_sync_end.strftime("%Y-%m-%d"),
                                store_id,
                            )

                        if hb_result["success"]:
                            if hb_result["inserted"] == 0 and hb_result["skipped"] == 0:
                                st.info("Bu tarih aralığında yeni sipariş bulunamadı.")
                            else:
                                st.markdown(
                                    f"""<div class="success-box">
                                    ✅ Senkronizasyon tamamlandı!<br>
                                    <b>{hb_result['inserted']:,} yeni sipariş</b> eklendi.
                                    {f"({hb_result['skipped']:,} tekrar atlandı.)" if hb_result['skipped'] else ""}
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                                if st.button("📊 Dashboard'a Git", key="hb_api_goto_dash"):
                                    _go("dashboard")

                            if hb_result.get("raw_sample"):
                                with st.expander("🔍 Ham API Yanıtı (alan adı doğrulama için)"):
                                    st.caption(
                                        "Hepsiburada API alan adları henüz resmi dokümandan doğrulanamadı. "
                                        "Müşteri adı, tarih veya tutar bilgileri yanlış görünüyorsa bu ham "
                                        "yanıttaki gerçek alan adlarını geliştiriciyle paylaşın."
                                    )
                                    st.json(hb_result["raw_sample"])
                        else:
                            st.error(f"❌ Hata: {hb_result['error']}")

    with tab_sample:
        st.markdown(
            """<div class="info-box">
            Gerçek veriniz yokken ReOrder'ı test etmek için 120 müşteri ve ~200 siparişten
            oluşan sentetik veri yükleyin.
            </div>""",
            unsafe_allow_html=True,
        )
        n_cust = st.slider("Müşteri sayısı", 30, 300, 120, step=10)
        if st.button("🎲 Örnek Veri Oluştur & Yükle", type="primary"):
            with st.spinner("Örnek veri oluşturuluyor…"):
                seed = (store_id or 42) % (2 ** 31)
                sample_df = generate_sample_orders(
                    n_customers=n_cust,
                    seed=seed,
                    store_name=store_name,
                )
                imp = import_to_db(sample_df, user["id"], batch="sample_data", store_id=store_id)
                st.cache_data.clear()
            st.session_state["_sample_done"] = {"inserted": imp["inserted"], "skipped": imp["skipped"], "n_cust": n_cust}
            st.rerun()

        if st.session_state.get("_sample_done"):
            res = st.session_state["_sample_done"]
            if res["inserted"] == 0 and res.get("skipped", 0) > 0:
                _msg = (f"ℹ️ Örnek veri zaten yüklü ({res['skipped']:,} sipariş mevcut), "
                        "yeni kayıt eklenmedi.")
            else:
                _msg = (f"🎉 <b>{res['inserted']:,} örnek sipariş</b> yüklendi! "
                        f"{res['n_cust']} müşteri için 12 aylık veri hazır.")
            st.markdown(
                f'<div class="success-box">{_msg}</div>',
                unsafe_allow_html=True,
            )
            if st.button("📊 Dashboard'a Git"):
                del st.session_state["_sample_done"]
                _go("dashboard")

    with tab_manage:
        m = get_summary_metrics(user["id"], store_id)
        if m["has_data"]:
            st.markdown(
                f"""<div class="warn-box">
                ⚠️ Şu anda <b>{m['total_orders']:,} sipariş</b> kayıtlı.
                Tüm verileri silmek geri alınamaz!
                </div>""",
                unsafe_allow_html=True,
            )
            confirm = st.checkbox("Evet, tüm sipariş verilerimi silmek istiyorum")
            if confirm:
                if st.button("🗑️ Tüm Verileri Sil", type="primary"):
                    cnt = delete_all_orders(user["id"], store_id)
                    st.success(f"{cnt:,} sipariş silindi.")
                    st.rerun()
        else:
            st.info("Henüz veri yüklenmemiş.")
