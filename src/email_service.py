"""
email_service.py — SMTP e-posta servisi ve kampanya şablonları.

Segment bazlı kampanya raporları hazırlayıp mağaza sahibine gönderir.
Müşteri e-postaları Trendyol'dan alınamadığı için rapor mağaza sahibine iletilir;
satıcı listeyi kendi kanallarından (WhatsApp, Trendyol mesajlaşma vb.) kullanabilir.
"""
from __future__ import annotations

import smtplib
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.database import get_connection


# ─────────────────────────────────────────────────────────────────────────────
# Segment kampanya şablonları
# ─────────────────────────────────────────────────────────────────────────────

SEGMENT_TEMPLATES: dict[str, dict] = {
    "Risk Altında": {
        "emoji": "⚠️",
        "color": "#EF4444",
        "tanim": "Son 90+ gün alışveriş yapmayan, 2–3 sipariş geçmişi olan müşteriler",
        "konu": "Sizi özledik! Yeni ürünlerimiz var",
        "mesaj": (
            "Merhaba {musteri_adi},\n\n"
            "Bir süredir alışveriş yapmadığınızı fark ettik ve sizi özledik! 🛍️\n\n"
            "Son siparişinizden bu yana {gun} gün geçti. "
            "{magaza_adi}'ndeki yeni ürünlerimize göz atmak ister misiniz?\n\n"
            "Her zaman yanınızdayız,\n"
            "{magaza_adi} Ekibi"
        ),
        "whatsapp": (
            "Merhaba! Bir süredir alışveriş yapmadınız, sizi özledik 🛍️ "
            "{magaza_adi} olarak yeni ürünlerimize göz atmanızı öneririz. İyi günler!"
        ),
    },
    "Kaybolma Riski": {
        "emoji": "🚨",
        "color": "#6B7280",
        "tanim": "Son 90+ gün alışveriş yapmayan, 4+ sipariş geçmişi olan değerli müşteriler",
        "konu": "Geri dönün, sizi bekliyoruz!",
        "mesaj": (
            "Merhaba {musteri_adi},\n\n"
            "Uzun süredir görüşemedik. {gun} gündür mağazamızda sizi göremedik. 😔\n\n"
            "{magaza_adi} olarak sizi yeniden aramızda görmekten mutluluk duyarız.\n\n"
            "Sevgilerle,\n"
            "{magaza_adi} Ekibi"
        ),
        "whatsapp": (
            "Merhaba! {magaza_adi} olarak sizi uzun süredir göremedik 😊 "
            "Tekrar bekleriz, iyi günler!"
        ),
    },
    "Tek Alışveriş": {
        "emoji": "💫",
        "color": "#9CA3AF",
        "tanim": "Sadece bir kez alışveriş yapıp 90+ gün geri dönmeyen müşteriler",
        "konu": "İlk alışverişinizden memnun kaldınız mı?",
        "mesaj": (
            "Merhaba {musteri_adi},\n\n"
            "{magaza_adi}'nden ilk alışverişinizi yaptığınız için teşekkür ederiz! 🎉\n\n"
            "Umarız ürününüzden memnun kaldınız. "
            "Yeni koleksiyonumuzu da incelemenizi öneririz.\n\n"
            "Her zaman memnuniyetiniz için buradayız,\n"
            "{magaza_adi} Ekibi"
        ),
        "whatsapp": (
            "Merhaba! {magaza_adi}'nden alışveriş yaptığınız için teşekkürler 🎉 "
            "Yeni ürünlerimizi de beğeneceğinizi umuyoruz. İyi günler!"
        ),
    },
    "Sadık Müşteri": {
        "emoji": "⭐",
        "color": "#10B981",
        "tanim": "Son 90 gün içinde 4+ sipariş veren en sadık müşteriler",
        "konu": "VIP müşterimiz olduğunuz için teşekkürler!",
        "mesaj": (
            "Merhaba {musteri_adi},\n\n"
            "{magaza_adi} ailesinin değerli bir üyesi olduğunuz için teşekkür ederiz! ⭐\n\n"
            "Sürekli tercihleriniz bizim için çok değerli. "
            "Sizi en iyi şekilde ağırlamak için her zaman çalışıyoruz.\n\n"
            "Saygılarımızla,\n"
            "{magaza_adi} Ekibi"
        ),
        "whatsapp": (
            "Merhaba! Değerli müşterimiz olduğunuz için teşekkürler ⭐ "
            "Sizi tanımak her zaman bir ayrıcalık. İyi günler!"
        ),
    },
}

ALL_SEGMENTS = list(SEGMENT_TEMPLATES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# SMTP yapılandırması
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SMTPConfig:
    host: str
    port: int
    user: str
    password: str
    from_email: str
    from_name: str = "ReOrder"
    use_tls: bool = True


def save_smtp_settings(user_id: int, config: SMTPConfig) -> None:
    """SMTP ayarlarını user_settings tablosuna kaydeder."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO user_settings
            (user_id, smtp_host, smtp_port, smtp_user, smtp_pass,
             smtp_from_email, smtp_from_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            smtp_host       = excluded.smtp_host,
            smtp_port       = excluded.smtp_port,
            smtp_user       = excluded.smtp_user,
            smtp_pass       = excluded.smtp_pass,
            smtp_from_email = excluded.smtp_from_email,
            smtp_from_name  = excluded.smtp_from_name
        """,
        (user_id, config.host, config.port, config.user,
         config.password, config.from_email, config.from_name),
    )
    conn.commit()
    conn.close()


def load_smtp_settings(user_id: int) -> Optional[SMTPConfig]:
    """Kaydedilmiş SMTP ayarlarını yükler; kayıt yoksa None döndürür."""
    conn = get_connection()
    row = conn.execute(
        "SELECT smtp_host, smtp_port, smtp_user, smtp_pass, "
        "smtp_from_email, smtp_from_name "
        "FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()

    if not row or not row["smtp_host"]:
        return None

    return SMTPConfig(
        host=row["smtp_host"],
        port=int(row["smtp_port"] or 587),
        user=row["smtp_user"] or "",
        password=row["smtp_pass"] or "",
        from_email=row["smtp_from_email"] or "",
        from_name=row["smtp_from_name"] or "ReOrder",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Kampanya geçmişi
# ─────────────────────────────────────────────────────────────────────────────

def save_campaign_log(
    user_id: int,
    segment: str,
    subject: str,
    sent_to: str,
    customer_count: int,
    store_id: int | None = None,
) -> None:
    """Gönderilen kampanyayı campaigns tablosuna kaydeder."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO campaigns (user_id, store_id, segment, subject, sent_to, customer_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, store_id, segment, subject, sent_to, customer_count),
    )
    conn.commit()
    conn.close()


def load_campaign_history(user_id: int, store_id: int | None = None) -> list[dict]:
    """Kullanıcının (veya mağazanın) kampanya geçmişini döndürür (en yeni önce)."""
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT segment, subject, sent_to, customer_count, sent_at "
            "FROM campaigns WHERE user_id = ? AND store_id = ? ORDER BY sent_at DESC LIMIT 50",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT segment, subject, sent_to, customer_count, sent_at "
            "FROM campaigns WHERE user_id = ? ORDER BY sent_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Şablon yardımcısı
# ─────────────────────────────────────────────────────────────────────────────

def build_template(template_text: str, musteri_adi: str, gun: int, magaza_adi: str) -> str:
    """Şablon değişkenlerini ({musteri_adi}, {gun}, {magaza_adi}) doldurur."""
    return (
        template_text
        .replace("{musteri_adi}", musteri_adi)
        .replace("{gun}", str(gun))
        .replace("{magaza_adi}", magaza_adi)
    )


# ─────────────────────────────────────────────────────────────────────────────
# E-posta oluşturma & gönderme
# ─────────────────────────────────────────────────────────────────────────────

def _ipv4_connect(host: str, port: int, timeout: int, source_address=None) -> socket.socket:
    """IPv4 üzerinden bağlanır. Bazı barındırma ortamlarında (örn. Render) container'ın
    IPv6 route'u olmadığı halde DNS AAAA kaydı döndüğünde socket.create_connection
    önce IPv6'yı deneyip 'Network is unreachable' hatasıyla başarısız olabiliyor."""
    addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    ipv4_addr = addr_info[0][4]
    return socket.create_connection(ipv4_addr, timeout, source_address=source_address)


class _IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _ipv4_connect(host, port, timeout, source_address=self.source_address)


class _IPv4SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        sock = _ipv4_connect(host, port, timeout, source_address=self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def _send_smtp(config: SMTPConfig, to_email: str, msg: MIMEMultipart) -> None:
    """SMTP üzerinden e-posta gönderir. Port 465 → SSL, diğerleri → STARTTLS."""
    context = ssl.create_default_context()
    if config.port == 465:
        with _IPv4SMTP_SSL(config.host, config.port, context=context, timeout=20) as srv:
            srv.login(config.user, config.password)
            srv.sendmail(config.from_email, to_email, msg.as_string())
    else:
        with _IPv4SMTP(config.host, config.port, timeout=20) as srv:
            srv.ehlo()
            if config.use_tls:
                srv.starttls(context=context)
            srv.login(config.user, config.password)
            srv.sendmail(config.from_email, to_email, msg.as_string())


def send_test_email(config: SMTPConfig, to_email: str) -> dict:
    """SMTP ayarlarını doğrulamak için test e-postası gönderir."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ ReOrder SMTP Bağlantı Testi"
        msg["From"] = f"{config.from_name} <{config.from_email}>"
        msg["To"] = to_email

        html = """<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:0;">
  <div style="background:linear-gradient(135deg,#F27A1A,#D4621A);border-radius:12px 12px 0 0;padding:22px 30px;">
    <h2 style="color:white;margin:0;font-size:1.3rem;">🔄 ReOrder — SMTP Testi Başarılı!</h2>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;padding:24px 30px;background:white;">
    <p style="color:#374151;line-height:1.6;">
      E-posta ayarlarınız doğru şekilde yapılandırılmış. ✅<br>
      Artık segment bazlı kampanya raporları gönderebilirsiniz.
    </p>
    <hr style="border:none;border-top:1px solid #f0f0f0;margin:16px 0;">
    <p style="color:#9ca3af;font-size:.8rem;margin:0;">
      Bu e-posta ReOrder uygulamasından otomatik gönderilmiştir.
    </p>
  </div>
</body></html>"""

        msg.attach(MIMEText(html, "html", "utf-8"))
        _send_smtp(config, to_email, msg)
        return {"success": True, "message": "✅ Test e-postası başarıyla gönderildi!"}
    except Exception as exc:
        return {"success": False, "message": f"❌ Hata: {exc}"}


def _campaign_html(
    store_name: str,
    segment: str,
    customers: list[dict],
    template_text: str,
) -> str:
    """Kampanya raporu için HTML e-posta içeriği üretir."""
    tmpl = SEGMENT_TEMPLATES.get(segment, {})
    color = tmpl.get("color", "#F27A1A")
    emoji = tmpl.get("emoji", "📧")

    # İlk müşteri önizlemesi
    if customers:
        first = customers[0]
        preview_msg = build_template(
            template_text,
            first.get("customer_identifier", "Müşteri"),
            int(first.get("days_since_last", 30)),
            store_name,
        )
    else:
        preview_msg = template_text

    preview_html = preview_msg.replace("\n", "<br>")

    # Müşteri satırları (max 60)
    rows_html = ""
    for c in customers[:60]:
        rev = c.get("total_revenue", 0)
        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f5f5f5;'>{c.get('customer_identifier','')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f5f5f5;text-align:center;'>{c.get('total_orders',0)}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f5f5f5;text-align:right;'>₺{float(rev):,.2f}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f5f5f5;text-align:center;'>{c.get('days_since_last',0)} gün</td>"
            f"</tr>"
        )

    extra = ""
    if len(customers) > 60:
        extra = f"<p style='color:#9ca3af;font-size:.8rem;margin:8px 0 0;'>+ {len(customers)-60} müşteri daha — tam listeyi CSV olarak indirin</p>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f8fafc;margin:0;padding:16px;">
<div style="max-width:700px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 14px rgba(0,0,0,.1);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#F27A1A,#D4621A);padding:22px 30px;">
    <h1 style="color:white;margin:0;font-size:1.3rem;">🔄 ReOrder — Kampanya Raporu</h1>
    <p style="color:rgba(255,255,255,.85);margin:5px 0 0;font-size:.85rem;">
      {store_name} &middot; {datetime.now().strftime('%d.%m.%Y %H:%M')}
    </p>
  </div>

  <!-- Segment etiketi -->
  <div style="padding:16px 30px;border-bottom:1px solid #e5e7eb;">
    <span style="background:{color}22;color:{color};padding:5px 14px;border-radius:20px;font-weight:700;font-size:.9rem;">
      {emoji} {segment}
    </span>
    <span style="margin-left:12px;color:#6b7280;font-size:.9rem;">
      <b>{len(customers)}</b> müşteri bu segmentte
    </span>
  </div>

  <!-- Mesaj şablonu önizleme -->
  <div style="padding:18px 30px;background:#fafafa;border-bottom:1px solid #e5e7eb;">
    <h3 style="color:#1a1a2e;margin:0 0 10px;font-size:.95rem;">
      📝 Mesaj Şablonu (1. müşteri önizlemesi)
    </h3>
    <div style="background:white;border:1px solid #e5e7eb;border-radius:8px;padding:14px;
                color:#374151;font-size:.87rem;line-height:1.7;">
      {preview_html}
    </div>
  </div>

  <!-- Müşteri listesi -->
  <div style="padding:18px 30px;">
    <h3 style="color:#1a1a2e;margin:0 0 10px;font-size:.95rem;">👥 Müşteri Listesi</h3>
    <table style="width:100%;border-collapse:collapse;font-size:.84rem;">
      <thead>
        <tr style="background:#f3f4f6;">
          <th style="padding:8px 10px;text-align:left;color:#6b7280;font-weight:600;">Müşteri</th>
          <th style="padding:8px 10px;text-align:center;color:#6b7280;font-weight:600;">Sipariş</th>
          <th style="padding:8px 10px;text-align:right;color:#6b7280;font-weight:600;">Toplam</th>
          <th style="padding:8px 10px;text-align:center;color:#6b7280;font-weight:600;">Son Alış.</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    {extra}
  </div>

  <!-- Footer -->
  <div style="padding:14px 30px;background:#1a1a2e;text-align:center;">
    <p style="color:rgba(255,255,255,.4);margin:0;font-size:.78rem;">
      ReOrder · Trendyol Müşteri Retention Platformu
    </p>
  </div>
</div>
</body></html>"""


def send_campaign_report(
    config: SMTPConfig,
    to_email: str,
    store_name: str,
    segment: str,
    customers: list[dict],
    custom_template: str,
) -> dict:
    """
    Kampanya raporunu mağaza sahibine e-posta ile gönderir.

    Dönüş: {'success': bool, 'message': str, 'subject': str}
    """
    try:
        subject = f"📧 {store_name} — {segment} Kampanyası ({len(customers)} müşteri)"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.from_name} <{config.from_email}>"
        msg["To"] = to_email

        html = _campaign_html(store_name, segment, customers, custom_template)
        msg.attach(MIMEText(html, "html", "utf-8"))

        _send_smtp(config, to_email, msg)
        return {
            "success": True,
            "message": f"✅ {len(customers)} müşteri için kampanya raporu gönderildi!",
            "subject": subject,
        }
    except Exception as exc:
        return {"success": False, "message": f"❌ Hata: {exc}", "subject": ""}


# ─────────────────────────────────────────────────────────────────────────────
# Haftalık Özet E-posta
# ─────────────────────────────────────────────────────────────────────────────

def _weekly_html(
    store_name: str,
    metrics: dict,
    comparison: dict,
    top_customers: list[dict],
) -> str:
    rev = metrics.get("revenue", 0)
    orders = metrics.get("orders", 0)
    new_c = metrics.get("new_customers", 0)
    ret = metrics.get("retention_rate", 0)
    delta_rev = comparison.get("delta_revenue_pct", 0)
    delta_ord = comparison.get("delta_orders_pct", 0)
    delta_color = "#10B981" if delta_rev >= 0 else "#EF4444"
    delta_sign  = "+" if delta_rev >= 0 else ""

    def fmt(v):
        return f"₺{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    top_rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #f0f2f7;'>{i+1}. {r.get('musteri','—')[:30]}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #f0f2f7;text-align:right;'>{fmt(r.get('ltv',0))}</td></tr>"
        for i, r in enumerate(top_customers[:5])
    )

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;background:#f8fafc;padding:20px;">
      <div style="background:linear-gradient(135deg,#F28500,#D46000);border-radius:14px;padding:24px;text-align:center;margin-bottom:20px;">
        <div style="font-size:28px;margin-bottom:4px;">🔄 ReOrder</div>
        <h2 style="color:#fff;margin:0;font-size:20px;">Haftalık Özet Raporu</h2>
        <p style="color:rgba(255,255,255,.75);margin:6px 0 0;font-size:13px;">{store_name} · {datetime.now().strftime('%d.%m.%Y')}</p>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
        <div style="background:#fff;border-radius:10px;padding:16px;border-left:4px solid #F28500;box-shadow:0 2px 8px rgba(0,0,0,.06);">
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">BU AY GELİR</div>
          <div style="font-size:22px;font-weight:800;color:#0f1a35;">{fmt(rev)}</div>
          <div style="font-size:12px;color:{delta_color};margin-top:3px;">{delta_sign}{delta_rev:.1f}% geçen aya göre</div>
        </div>
        <div style="background:#fff;border-radius:10px;padding:16px;border-left:4px solid #3B82F6;box-shadow:0 2px 8px rgba(0,0,0,.06);">
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">SİPARİŞ</div>
          <div style="font-size:22px;font-weight:800;color:#0f1a35;">{orders:,}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:3px;">{delta_sign}{delta_ord:.1f}% geçen aya göre</div>
        </div>
        <div style="background:#fff;border-radius:10px;padding:16px;border-left:4px solid #10B981;box-shadow:0 2px 8px rgba(0,0,0,.06);">
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">YENİ MÜŞTERİ</div>
          <div style="font-size:22px;font-weight:800;color:#0f1a35;">{new_c}</div>
        </div>
        <div style="background:#fff;border-radius:10px;padding:16px;border-left:4px solid #8B5CF6;box-shadow:0 2px 8px rgba(0,0,0,.06);">
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">RETENTİON</div>
          <div style="font-size:22px;font-weight:800;color:#0f1a35;">%{ret:.1f}</div>
        </div>
      </div>

      {'<div style="background:#fff;border-radius:10px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.06);margin-bottom:20px;"><div style="font-size:13px;font-weight:700;color:#0f1a35;margin-bottom:10px;">⭐ En İyi Müşteriler</div><table style="width:100%;border-collapse:collapse;font-size:13px;">' + top_rows + '</table></div>' if top_rows else ''}

      <div style="text-align:center;padding:16px 0;border-top:1px solid #e8edf5;color:#9ca3af;font-size:11px;">
        ReOrder © 2026 · Bu raporu devre dışı bırakmak için Ayarlar → Haftalık Rapor
      </div>
    </div>
    """


def send_weekly_summary(
    config: SMTPConfig,
    to_email: str,
    store_name: str,
    metrics: dict,
    comparison: dict,
    top_customers: list[dict],
) -> dict:
    """Haftalık özet raporunu e-posta ile gönderir."""
    try:
        subject = f"📊 {store_name} — Haftalık ReOrder Raporu ({datetime.now().strftime('%d.%m.%Y')})"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.from_name} <{config.from_email}>"
        msg["To"] = to_email
        html = _weekly_html(store_name, metrics, comparison, top_customers)
        msg.attach(MIMEText(html, "html", "utf-8"))
        _send_smtp(config, to_email, msg)
        return {"success": True, "message": "✅ Haftalık rapor gönderildi!"}
    except Exception as exc:
        return {"success": False, "message": f"❌ Hata: {exc}"}
