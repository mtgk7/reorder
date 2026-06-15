"""pages/upload.py — Veri Yükle sayfası"""
from __future__ import annotations
import streamlit as st

from src.parser import parse_trendyol_file, import_to_db, generate_sample_orders
from src.trendyol_api import save_credentials, load_credentials, sync_orders, TrendyolClient
from src.analytics import get_summary_metrics
from src.database import delete_all_orders
from src.ui_helpers import _section, _header, _go


def run() -> None:
    user = st.session_state.user
    store_id = st.session_state.get("active_store_id")
    stores = st.session_state.get("stores", [])
    store_name = next((s["store_name"] for s in stores if s["id"] == store_id), user["store_name"])
    _header("📁", "Veri Yükle", "Trendyol sipariş raporunuzu içe aktarın")

    tab_file, tab_api, tab_sample, tab_manage = st.tabs(
        ["📂 Dosya Yükle", "🔌 Trendyol API", "🎲 Örnek Veri", "🗑️ Veri Yönetimi"]
    )

    with tab_file:
        st.markdown(
            """<div class="info-box">
            <b>Nasıl yapılır?</b><br>
            Trendyol Satıcı Paneli → <b>Siparişlerim</b> → <b>Excel İndir</b> butonuyla indirdiğiniz
            <code>.xlsx</code> veya <code>.csv</code> dosyasını buraya yükleyin.
            Sistem sütunları otomatik tanır.
            </div>""",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Trendyol Sipariş Raporu (.xlsx, .csv)",
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
                    """<div class="warn-box">
                    <b>İpucu:</b> Trendyol'dan indirdiğiniz orijinal Excel dosyasını (formatı değiştirmeden) yükleyin.
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
            st.session_state["_sample_done"] = {"inserted": imp["inserted"], "n_cust": n_cust}
            st.rerun()

        if st.session_state.get("_sample_done"):
            res = st.session_state["_sample_done"]
            st.markdown(
                f"""<div class="success-box">
                🎉 <b>{res['inserted']:,} örnek sipariş</b> yüklendi!
                {res['n_cust']} müşteri için 12 aylık veri hazır.
                </div>""",
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
