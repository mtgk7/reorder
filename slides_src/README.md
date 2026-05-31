# Login Carousel Slayt Kaynakları

`app.py` içindeki login carousel'i 4 statik görsel kullanır: `assets/slide_*.png`.
Bu klasör o görsellerin **kaynak HTML'leridir** (1280×720, kod ile çizilmiş).

| Kaynak | Üretilen görsel |
|--------|-----------------|
| `dashboard.html` | `assets/slide_dashboard.png` |
| `cohort.html`    | `assets/slide_cohort.png` |
| `segments.html`  | `assets/slide_segments.png` |
| `pdf.html`       | `assets/slide_pdf.png` |

## Bir slaytı düzenleyip PNG'yi yeniden üretmek

1. İlgili `.html` dosyasındaki metin/rakamları düzenle.
2. Klasörü yerelde servis et:
   ```bash
   cd slides_src && python -m http.server 8777
   ```
3. Tarayıcıda `http://localhost:8777/dashboard.html` aç, pencereyi **1280×720**
   yap ve ekran görüntüsü al; ya da headless bir araçla (Playwright vb.)
   1280×720 viewport'ta screenshot al.
4. PNG'yi ilgili `assets/slide_*.png` üzerine kaydet.

> Carousel `app.py`'de görselleri yükleme anında WebP'ye (tam 1280px, q90) sıkıştırıp
> base64 gömer — `assets/` PNG'lerini güncellemen yeterli, başka değişiklik gerekmez.
> `@st.cache_data` nedeniyle değişikliğin görünmesi için uygulamayı yeniden başlat.
