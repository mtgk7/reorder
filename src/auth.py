"""
auth.py — Kullanıcı kaydı, giriş ve bcrypt tabanlı şifreleme.
PostgreSQL ve SQLite ile uyumludur.
"""
import re
import secrets
import bcrypt
from src.database import get_connection


# ─────────────────────────────────────────────────────────────────────────────
# Şifreleme
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Şifreyi bcrypt ile hash'ler."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Şifreyi hash ile karşılaştırır."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Doğrulama yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def _validate_email(email: str) -> str | None:
    """E-posta formatını kontrol eder. Hata varsa mesaj, yoksa None döner."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        return "Geçerli bir e-posta adresi girin."
    return None


def _validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Şifre en az 8 karakter olmalıdır."
    if not any(c.isdigit() for c in password):
        return "Şifre en az bir rakam içermelidir."
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Temel işlemler
# ─────────────────────────────────────────────────────────────────────────────

def register_user(email: str, password: str, store_name: str) -> dict:
    """
    Yeni kullanıcı kaydeder.

    Dönüş:
        {'success': True,  'user': {'id', 'email', 'store_name'}}
        {'success': False, 'error': '<mesaj>'}
    """
    email = email.strip().lower()
    store_name = store_name.strip()

    if not store_name:
        return {"success": False, "error": "Mağaza adı boş bırakılamaz."}

    err = _validate_email(email)
    if err:
        return {"success": False, "error": err}

    err = _validate_password(password)
    if err:
        return {"success": False, "error": err}

    pw_hash = hash_password(password)
    conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (email, password_hash, store_name)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            (email, pw_hash, store_name),
        )
        # RETURNING sonucunu tüket (SQLite'ı commit öncesi serbest bırakır)
        # PostgreSQL _PgCursor zaten execute() içinde tüketti, fetchone() None döner
        row = cur.fetchone()
        user_id = row["id"] if row else cur.lastrowid
        conn.commit()
        conn.close()
        return {
            "success": True,
            "user": {"id": user_id, "email": email, "store_name": store_name},
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg or "already exists" in msg:
            return {"success": False, "error": "Bu e-posta adresi zaten kayıtlı."}
        return {"success": False, "error": f"Kayıt sırasında hata: {exc}"}


def login_user(email: str, password: str) -> dict:
    """
    Kullanıcı girişi yapar.

    Dönüş:
        {'success': True,  'user': {'id', 'email', 'store_name'}}
        {'success': False, 'error': '<mesaj>'}
    """
    email = email.strip().lower()

    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, store_name, plan, plan_period FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    conn.close()

    if row is None or not verify_password(password, row["password_hash"]):
        return {"success": False, "error": "E-posta veya şifre hatalı."}

    return {
        "success": True,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "store_name": row["store_name"],
            "plan": row["plan"] or "Starter",
            "plan_period": row["plan_period"] or "m",
        },
    }


def update_store_name(user_id: int, new_name: str) -> dict:
    """Mağaza adını günceller."""
    new_name = new_name.strip()
    if not new_name:
        return {"success": False, "error": "Mağaza adı boş olamaz."}
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE users SET store_name = ? WHERE id = ?",
            (new_name, user_id),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Oturum token yönetimi (yenileme sonrası otomatik giriş)
# ─────────────────────────────────────────────────────────────────────────────

def create_session_token(user_id: int) -> str:
    """
    Güvenli rastgele token üretir, 30 günlük geçerlilikle DB'ye kaydeder.
    Dönüş: token string
    """
    token = secrets.token_urlsafe(32)
    conn = get_connection()
    conn.execute(
        "INSERT INTO session_tokens (user_id, token) VALUES (?, ?)",
        (user_id, token),
    )
    conn.commit()
    conn.close()
    return token


def verify_session_token(token: str) -> dict | None:
    """
    Token geçerliyse ve süresi dolmamışsa kullanıcı bilgilerini döner, yoksa None.
    """
    if not token or len(token) < 10:
        return None
    conn = get_connection()
    row = conn.execute(
        """
        SELECT u.id, u.email, u.store_name, u.plan, u.plan_period
        FROM   session_tokens st
        JOIN   users u ON u.id = st.user_id
        WHERE  st.token = ?
          AND  (st.expires_at IS NULL OR st.expires_at > datetime('now'))
        """,
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "store_name": row["store_name"],
        "plan": row["plan"] or "Starter",
        "plan_period": row["plan_period"] or "m",
    }


def delete_session_token(token: str) -> None:
    """Token'ı siler (logout)."""
    if not token:
        return
    conn = get_connection()
    conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def send_reset_email(email: str, token: str) -> dict:
    """Şifre sıfırlama e-postası gönderir.
    Önce RESEND_API_KEY'e bakar (Render free tier için önerilir),
    yoksa SMTP env vars ile dener.
    """
    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    resend_api_key = os.environ.get("RESEND_API_KEY", "")
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM_EMAIL", smtp_user)
    app_url   = os.environ.get("APP_URL", "https://reorder-81nz.onrender.com").rstrip("/")

    if not (resend_api_key or (smtp_host and smtp_user and smtp_pass)):
        return {"success": False, "error": "no_smtp"}

    reset_link = f"{app_url}/?reset_token={token}"

    html = f"""
<!DOCTYPE html><html lang="tr"><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:#f0f4fa;margin:0;padding:20px;">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;
    box-shadow:0 4px 24px rgba(0,0,0,.08);">
  <div style="background:linear-gradient(135deg,#1a2744,#0f1a35);padding:28px 32px;text-align:center;">
    <div style="font-size:1.5rem;font-weight:900;color:#fff;">🔄 ReOrder</div>
    <div style="font-size:.76rem;color:rgba(255,255,255,.45);margin-top:4px;">Şifre Sıfırlama</div>
  </div>
  <div style="padding:32px;">
    <p style="color:#374151;font-size:.93rem;margin:0 0 12px;">Merhaba,</p>
    <p style="color:#374151;font-size:.9rem;line-height:1.65;margin:0 0 24px;">
      ReOrder hesabınız (<strong>{email}</strong>) için şifre sıfırlama talebinde bulundunuz.<br>
      Aşağıdaki butona tıklayarak yeni şifrenizi belirleyebilirsiniz.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{reset_link}"
         style="background:linear-gradient(135deg,#F28500,#D46000);color:#fff;text-decoration:none;
                border-radius:10px;padding:14px 32px;font-weight:800;font-size:.93rem;
                display:inline-block;box-shadow:0 4px 16px rgba(242,133,0,.4);">
        🔑 Şifremi Sıfırla
      </a>
    </div>
    <p style="color:#9ca3af;font-size:.77rem;line-height:1.6;margin:0;">
      Bu bağlantı <strong>1 saat</strong> geçerlidir ve yalnızca bir kez kullanılabilir.<br>
      Bu talebi siz yapmadıysanız bu e-postayı görmezden gelebilirsiniz.
    </p>
  </div>
  <div style="background:#f8faff;border-top:1px solid #e8edf5;padding:14px 32px;text-align:center;">
    <p style="color:#9ca3af;font-size:.7rem;margin:0;">ReOrder © 2026 — Trendyol Retention Platformu</p>
  </div>
</div>
</body></html>
"""
    # ── Resend HTTP API (Render free tier'da çalışır) ─────────────────────────
    if resend_api_key:
        try:
            import urllib.request, json as _json
            # Resend: domain dogrulanmadiysa onboarding@resend.dev kullan
            resend_from = os.environ.get("RESEND_FROM_EMAIL", "ReOrder <onboarding@resend.dev>")
            payload = _json.dumps({
                "from": resend_from,
                "to": [email],
                "subject": "ReOrder — Şifre Sıfırlama",
                "html": html,
            }).encode()
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    return {"success": True}
                body = resp.read().decode()
                return {"success": False, "error": f"Resend {resp.status}: {body}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── SMTP fallback ─────────────────────────────────────────────────────────
    msg_obj = MIMEMultipart("alternative")
    msg_obj["Subject"] = "ReOrder — Şifre Sıfırlama"
    msg_obj["From"]    = f"ReOrder <{smtp_from}>"
    msg_obj["To"]      = email
    msg_obj.attach(MIMEText(html, "html"))
    try:
        import socket as _sock
        _orig_gai = _sock.getaddrinfo
        def _ipv4_gai(host, port, family=0, *a, **kw):
            return _orig_gai(host, port, _sock.AF_INET, *a, **kw)
        _sock.getaddrinfo = _ipv4_gai
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [email], msg_obj.as_string())
        finally:
            _sock.getaddrinfo = _orig_gai
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def reset_password_with_token(token: str, new_password: str) -> dict:
    """Token ile şifreyi sıfırlar; token geçersizse hata döner."""
    from src.database import verify_reset_token, use_reset_token

    user = verify_reset_token(token)
    if not user:
        return {"success": False, "error": "Bağlantı geçersiz veya süresi dolmuş (1 saat)."}

    err = _validate_password(new_password)
    if err:
        return {"success": False, "error": err}

    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user["id"]),
    )
    conn.commit()
    conn.close()
    use_reset_token(token)
    return {"success": True, "email": user["email"]}


def change_password(user_id: int, old_password: str, new_password: str) -> dict:
    """Şifreyi değiştirir."""
    conn = get_connection()
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()

    if not row or not verify_password(old_password, row["password_hash"]):
        return {"success": False, "error": "Mevcut şifre hatalı."}

    err = _validate_password(new_password)
    if err:
        return {"success": False, "error": err}

    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()
    conn.close()
    return {"success": True}
