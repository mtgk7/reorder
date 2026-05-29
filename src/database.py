"""
database.py — Veritabanı bağlantı yönetimi.
PostgreSQL (üretim/cloud) ve SQLite (yerel geliştirme) destekler.
DATABASE_URL ortam değişkeni veya Streamlit secrets ile yapılandırılır.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

# ─── DB URL tespiti ───────────────────────────────────────────────────────────

def _get_db_url() -> str | None:
    """DATABASE_URL'yi ortam değişkeninden veya Streamlit secrets'tan alır."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL")
    except Exception:
        return None


def _normalize_url(url: str) -> str:
    """Heroku/Supabase'in postgres:// önekini postgresql:// yapar."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


# ─── SQL uyumluluk dönüşümü ──────────────────────────────────────────────────

def _to_pg_sql(sql: str) -> str:
    """SQLite SQL sözdizimini PostgreSQL'e çevirir."""
    # ? → %s  (konumsal parametre)
    sql = sql.replace("?", "%s")
    # INSERT OR IGNORE INTO → INSERT INTO  (ON CONFLICT DO NOTHING alt satırda olmalı)
    sql = re.sub(
        r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
        "INSERT INTO",
        sql,
        flags=re.IGNORECASE,
    )
    # SQLite tarih fonksiyonları → PostgreSQL karşılıkları
    sql = re.sub(r"datetime\('now'\)", "NOW()", sql, flags=re.IGNORECASE)
    sql = re.sub(r"date\('now'\)", "CURRENT_DATE", sql, flags=re.IGNORECASE)
    return sql


# ─── PostgreSQL uyumluluk sarmalayıcılar ─────────────────────────────────────

class _PgCursor:
    """
    sqlite3.Cursor arayüzünü taklit eden psycopg2 cursor sarmalayıcı.
    execute() → ? yerine %s kullanır, RETURNING id sonucunu lastrowid'e atar.
    """

    def __init__(self, pg_conn) -> None:
        import psycopg2.extras
        self._cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.lastrowid: int | None = None
        self.rowcount: int = 0

    def execute(self, sql: str, params=None):
        sql = _to_pg_sql(sql)
        self._cur.execute(sql, params or ())
        self.rowcount = self._cur.rowcount
        # RETURNING id varsa satırı tüket ve lastrowid'e kaydet
        if re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
            row = self._cur.fetchone()
            if row:
                self.lastrowid = list(row.values())[0]
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def keys(self):
        if self._cur.description:
            return [d[0] for d in self._cur.description]
        return []


class _PgConnection:
    """
    sqlite3.Connection arayüzünü taklit eden psycopg2 bağlantı sarmalayıcı.
    get_connection() PostgreSQL modunda bu sınıfın örneğini döndürür.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def execute(self, sql: str, params=None) -> _PgCursor:
        cur = _PgCursor(self._conn)
        return cur.execute(sql, params)

    def cursor(self) -> _PgCursor:
        return _PgCursor(self._conn)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── Bağlantı fabrikası ──────────────────────────────────────────────────────

_DB_PATH = Path(__file__).parent.parent / "data" / "reorder.db"


def get_connection():
    """
    Veritabanı bağlantısı döndürür.

    - DATABASE_URL ayarlıysa → PostgreSQL (_PgConnection)
    - Ayarlı değilse         → SQLite (sqlite3.Connection, yerel geliştirme)
    """
    db_url = _get_db_url()
    if db_url:
        import psycopg2
        conn = psycopg2.connect(_normalize_url(db_url))
        return _PgConnection(conn)

    # SQLite (yerel)
    os.makedirs(_DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Şema başlatma ───────────────────────────────────────────────────────────

def init_db() -> None:
    """Tüm tabloları ve indeksleri oluşturur (idempotent)."""
    db_url = _get_db_url()
    if db_url:
        _init_postgres(_normalize_url(db_url))
    else:
        _init_sqlite()


def _init_postgres(db_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            store_name    TEXT NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL,
            order_number        TEXT,
            customer_identifier TEXT NOT NULL,
            order_date          DATE NOT NULL,
            total_amount        REAL NOT NULL DEFAULT 0,
            status              TEXT,
            product_name        TEXT,
            quantity            INTEGER DEFAULT 1,
            import_batch        TEXT,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, order_number, customer_identifier)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id             INTEGER PRIMARY KEY,
            trendyol_seller_id  TEXT,
            trendyol_api_key    TEXT,
            trendyol_api_secret TEXT,
            last_sync_at        TIMESTAMPTZ,
            last_sync_count     INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days'),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user     ON orders(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(user_id, customer_identifier)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_date     ON orders(user_id, order_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_tokens  ON session_tokens(token)")

    _migrate_postgres(cur)

    conn.commit()
    conn.close()


def _migrate_postgres(cur) -> None:
    """PostgreSQL şemasını günceller: yeni sütunlar ve tablolar ekler (idempotent)."""
    smtp_cols = [
        ("smtp_host",       "TEXT"),
        ("smtp_port",       "INTEGER DEFAULT 587"),
        ("smtp_user",       "TEXT"),
        ("smtp_pass",       "TEXT"),
        ("smtp_from_email", "TEXT"),
        ("smtp_from_name",  "TEXT DEFAULT 'ReOrder'"),
    ]
    for col, dtype in smtp_cols:
        cur.execute(
            f"ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS {col} {dtype}"
        )

    # ── Çoklu Mağaza Desteği ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL,
            store_name      TEXT NOT NULL,
            ty_seller_id    TEXT,
            ty_api_key      TEXT,
            ty_api_secret   TEXT,
            last_sync_at    TIMESTAMPTZ,
            last_sync_count INTEGER DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stores_user ON stores(user_id)")

    # orders ve campaigns tablolarına store_id ekle
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id)")
    cur.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id)")

    # Mevcut kullanıcılar için varsayılan mağaza oluştur
    cur.execute("""
        INSERT INTO stores (user_id, store_name)
        SELECT u.id, u.store_name FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM stores s WHERE s.user_id = u.id)
    """)

    # Mevcut siparişleri varsayılan mağazaya bağla
    cur.execute("""
        UPDATE orders SET store_id = (
            SELECT id FROM stores WHERE user_id = orders.user_id LIMIT 1
        ) WHERE store_id IS NULL
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL,
            store_id       INTEGER REFERENCES stores(id),
            segment        TEXT NOT NULL,
            subject        TEXT,
            sent_to        TEXT,
            customer_count INTEGER DEFAULT 0,
            sent_at        TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)"
    )


def _init_sqlite() -> None:
    os.makedirs(_DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            store_name    TEXT NOT NULL,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            order_number        TEXT,
            customer_identifier TEXT NOT NULL,
            order_date          DATE NOT NULL,
            total_amount        REAL NOT NULL DEFAULT 0,
            status              TEXT,
            product_name        TEXT,
            quantity            INTEGER DEFAULT 1,
            import_batch        TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, order_number, customer_identifier)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id             INTEGER PRIMARY KEY,
            trendyol_seller_id  TEXT,
            trendyol_api_key    TEXT,
            trendyol_api_secret TEXT,
            last_sync_at        DATETIME,
            last_sync_count     INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at DATETIME DEFAULT (datetime('now', '+30 days')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user     ON orders(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(user_id, customer_identifier)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_date     ON orders(user_id, order_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_tokens  ON session_tokens(token)")

    _migrate_sqlite(cur)

    conn.commit()
    conn.close()


def _migrate_sqlite(cur) -> None:
    """SQLite şemasını günceller: yeni sütunlar ve tablolar ekler (idempotent)."""
    smtp_cols = [
        ("smtp_host",       "TEXT"),
        ("smtp_port",       "INTEGER DEFAULT 587"),
        ("smtp_user",       "TEXT"),
        ("smtp_pass",       "TEXT"),
        ("smtp_from_email", "TEXT"),
        ("smtp_from_name",  "TEXT DEFAULT 'ReOrder'"),
    ]
    for col, dtype in smtp_cols:
        try:
            cur.execute(f"ALTER TABLE user_settings ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    # ── Çoklu Mağaza Desteği ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            store_name      TEXT NOT NULL,
            ty_seller_id    TEXT,
            ty_api_key      TEXT,
            ty_api_secret   TEXT,
            last_sync_at    DATETIME,
            last_sync_count INTEGER DEFAULT 0,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stores_user ON stores(user_id)")
    except Exception:
        pass

    for col in ("store_id",):
        try:
            cur.execute(f"ALTER TABLE orders ADD COLUMN {col} INTEGER")
        except Exception:
            pass
        try:
            cur.execute(f"ALTER TABLE campaigns ADD COLUMN {col} INTEGER")
        except Exception:
            pass

    # Mevcut kullanıcılar için varsayılan mağaza oluştur
    cur.execute("""
        INSERT OR IGNORE INTO stores (user_id, store_name)
        SELECT u.id, u.store_name FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM stores s WHERE s.user_id = u.id)
    """)

    # Mevcut siparişleri varsayılan mağazaya bağla
    cur.execute("""
        UPDATE orders SET store_id = (
            SELECT id FROM stores WHERE user_id = orders.user_id LIMIT 1
        ) WHERE store_id IS NULL
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            store_id       INTEGER,
            segment        TEXT NOT NULL,
            subject        TEXT,
            sent_to        TEXT,
            customer_count INTEGER DEFAULT 0,
            sent_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)"
    )


# ─── Yardımcı fonksiyonlar ───────────────────────────────────────────────────

def get_stores(user_id: int) -> list[dict]:
    """Kullanıcıya ait tüm mağazaları döndürür."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM stores WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_store(user_id: int, store_name: str) -> int:
    """Yeni mağaza oluşturur; store_id döndürür."""
    conn = get_connection()
    db_url = _get_db_url()
    if db_url:
        cur = conn.execute(
            "INSERT INTO stores (user_id, store_name) VALUES (?, ?) RETURNING id",
            (user_id, store_name.strip()),
        )
        store_id = cur.lastrowid
    else:
        cur = conn.execute(
            "INSERT INTO stores (user_id, store_name) VALUES (?, ?)",
            (user_id, store_name.strip()),
        )
        store_id = cur.lastrowid
    conn.commit()
    conn.close()
    return store_id


def rename_store(store_id: int, user_id: int, new_name: str) -> None:
    """Mağaza adını günceller."""
    conn = get_connection()
    conn.execute(
        "UPDATE stores SET store_name = ? WHERE id = ? AND user_id = ?",
        (new_name.strip(), store_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_store(store_id: int, user_id: int) -> None:
    """Mağazayı ve bağlı tüm siparişleri siler."""
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE store_id = ? AND user_id = ?", (store_id, user_id))
    conn.execute("DELETE FROM stores WHERE id = ? AND user_id = ?", (store_id, user_id))
    conn.commit()
    conn.close()


def delete_all_orders(user_id: int, store_id: int | None = None) -> int:
    """Kullanıcıya (veya mağazaya) ait tüm siparişleri siler; silinen satır sayısını döndürür."""
    conn = get_connection()
    if store_id is not None:
        result = conn.execute(
            "DELETE FROM orders WHERE user_id = ? AND store_id = ?",
            (user_id, store_id),
        )
    else:
        result = conn.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return deleted
