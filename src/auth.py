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
        "SELECT id, email, password_hash, store_name FROM users WHERE email = ?",
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
        SELECT u.id, u.email, u.store_name
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
    return {"id": row["id"], "email": row["email"], "store_name": row["store_name"]}


def delete_session_token(token: str) -> None:
    """Token'ı siler (logout)."""
    if not token:
        return
    conn = get_connection()
    conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


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
