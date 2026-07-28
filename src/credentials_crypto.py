"""
credentials_crypto.py — Pazaryeri API kimlik bilgileri için ortak at-rest şifreleme.

CREDENTIALS_KEY env var'ı (Fernet anahtarı) ayarlıysa değerler şifrelenir.
Ayarlı değilse düz metin saklanır (geriye dönük uyumlu).
Mevcut düz-metin kayıtlar okunmaya devam eder — yalnızca yeni kayıtlar şifrelenir.

Trendyol, Hepsiburada vb. tüm pazaryeri API modülleri bu ortak yardımcıyı
kullanır — her modülün kendi şifreleme implementasyonunu yazmasını (ve
zamanla birbirinden sapmasını) önlemek için.
"""
from __future__ import annotations

_ENC_PREFIX = "enc:v1:"


def _get_fernet():
    """CREDENTIALS_KEY ayarlı ve cryptography kuruluysa Fernet nesnesi döner, yoksa None."""
    import os
    key = os.environ.get("CREDENTIALS_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception:
        return None


def enc(value: str) -> str:
    """Değeri şifreler (anahtar yoksa olduğu gibi döner)."""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def dec(value):
    """Şifreli değeri çözer; düz metin ise olduğu gibi döner."""
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    f = _get_fernet()
    if not f:
        return value  # anahtar kaybolduysa ham veriyi döndürme yerine olduğu gibi bırak
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return value
