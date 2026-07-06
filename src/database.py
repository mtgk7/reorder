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


def _pg_connect(db_url: str):
    """URL'yi parçalara ayırarak psycopg2 bağlantısı kurar (özel karakter sorunlarını önler)."""
    import psycopg2
    from urllib.parse import urlparse, unquote
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=(p.path or "/postgres").lstrip("/"),
    )


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


class _PooledPgConnection(_PgConnection):
    """_PgConnection that returns itself to the pool on close() instead of terminating."""

    def __init__(self, pool, pg_conn) -> None:
        super().__init__(pg_conn)
        self._pool = pool

    def close(self) -> None:
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __exit__(self, *args):
        self.close()


def _get_pg_pool():
    """Returns a module-level cached psycopg2 ThreadedConnectionPool (via st.cache_resource)."""
    try:
        import streamlit as st

        @st.cache_resource
        def _cached_pool():
            db_url = _get_db_url()
            if not db_url:
                return None
            from psycopg2.pool import ThreadedConnectionPool
            from urllib.parse import urlparse, unquote
            p = urlparse(_normalize_url(db_url))
            return ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                host=p.hostname,
                port=p.port or 5432,
                user=unquote(p.username or ""),
                password=unquote(p.password or ""),
                dbname=(p.path or "/postgres").lstrip("/"),
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )

        return _cached_pool()
    except Exception:
        return None


def get_connection():
    """
    Veritabanı bağlantısı döndürür.

    - DATABASE_URL ayarlıysa → PostgreSQL (_PooledPgConnection via connection pool)
    - Ayarlı değilse         → SQLite (sqlite3.Connection, yerel geliştirme)
    """
    db_url = _get_db_url()
    if db_url:
        pool = _get_pg_pool()
        if pool:
            try:
                raw_conn = pool.getconn()
                if raw_conn.closed:
                    pool.putconn(raw_conn, close=True)
                    raw_conn = pool.getconn()
                return _PooledPgConnection(pool, raw_conn)
            except Exception:
                pass
        # Pool yoksa veya tükendiyse direkt bağlantı aç
        return _PgConnection(_pg_connect(_normalize_url(db_url)))

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
    conn = _pg_connect(db_url)
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
    _migrate_orders_unique_pg(cur)

    conn.commit()
    conn.close()


def _migrate_orders_unique_pg(cur) -> None:
    """orders tablosunun UNIQUE constraint'ine store_id ekler (idempotent).
    SAVEPOINT kullanır — istisna tüm transaction'ı abort etmesin.
    """
    try:
        cur.execute("SAVEPOINT mou_drop")
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'orders' AND constraint_type = 'UNIQUE'
            AND constraint_name LIKE '%%order_number%%customer%%'
        """)
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else []
        for row in (rows or []):
            name = list(row.values())[0] if hasattr(row, 'values') else row[0]
            cur.execute(f"ALTER TABLE orders DROP CONSTRAINT IF EXISTS \"{name}\"")
        cur.execute("RELEASE SAVEPOINT mou_drop")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT mou_drop")
    try:
        cur.execute("SAVEPOINT mou_add")
        cur.execute("""
            ALTER TABLE orders ADD CONSTRAINT orders_user_store_order_cust_unique
            UNIQUE (user_id, store_id, order_number, customer_identifier)
        """)
        cur.execute("RELEASE SAVEPOINT mou_add")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT mou_add")


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

    # campaigns tablosunu store_id eklenmeden ÖNCE oluştur
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)")

    # orders ve campaigns tablolarına store_id ekle
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id)")
    cur.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id)")

    # Şehir ve sipariş saati kolonları
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS city TEXT DEFAULT ''")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_hour SMALLINT DEFAULT NULL")

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

    # ── Plan sistemi ──────────────────────────────────────────────────────────
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'Pro'")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_period TEXT DEFAULT 'm'")
    cur.execute("UPDATE users SET plan = 'Pro' WHERE plan IS NULL")
    cur.execute("UPDATE users SET plan_period = 'm' WHERE plan_period IS NULL")

    # ── Şifre Sıfırlama Token'ları ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '1 hour'),
            used       BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Hedef / KPI Takibi ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id        SERIAL PRIMARY KEY,
            user_id   INTEGER NOT NULL,
            store_id  INTEGER,
            metric    TEXT NOT NULL,
            target    REAL NOT NULL DEFAULT 0,
            UNIQUE(user_id, store_id, metric),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Referral Sistemi ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id             SERIAL PRIMARY KEY,
            referrer_id    INTEGER NOT NULL,
            referee_id     INTEGER,
            referral_code  TEXT NOT NULL UNIQUE,
            bonus_days     INTEGER DEFAULT 0,
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            used_at        TIMESTAMPTZ,
            FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (referee_id)  REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")

    # ── Haftalık Rapor Takibi ─────────────────────────────────────────────────
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_report_enabled BOOLEAN DEFAULT FALSE
    """)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_report_last_sent TIMESTAMPTZ
    """)

    # ── Stok Uyarı Sistemi (v10) ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_alerts (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL,
            store_id       INTEGER,
            product_name   TEXT NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_alerts_user ON stock_alerts(user_id)")

    # ── Ürün Yorumları ve Puanları (v10) ─────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_reviews (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            store_id     INTEGER,
            product_name TEXT NOT NULL,
            rating       REAL NOT NULL,
            review_text  TEXT,
            review_date  DATE,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_product_reviews_user ON product_reviews(user_id)")

    # ── Satıcı Skoru Takibi (v10) ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seller_scores (
            id                 SERIAL PRIMARY KEY,
            user_id            INTEGER NOT NULL,
            store_id           INTEGER,
            score_date         DATE NOT NULL,
            cargo_score        REAL,
            return_score       REAL,
            satisfaction_score REAL,
            note               TEXT,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seller_scores_user ON seller_scores(user_id)")

    # ── Rakip Fiyat Takibi (v10) ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS competitor_prices (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL,
            store_id         INTEGER,
            product_name     TEXT NOT NULL,
            my_price         REAL NOT NULL DEFAULT 0,
            competitor_name  TEXT,
            competitor_price REAL NOT NULL DEFAULT 0,
            competitor_url   TEXT,
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_competitor_prices_user ON competitor_prices(user_id)")

    # ── Kampanya ROI (v10) ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_roi (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            store_id      INTEGER,
            campaign_name TEXT NOT NULL,
            start_date    DATE NOT NULL,
            end_date      DATE NOT NULL,
            discount_pct  REAL NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaign_roi_user ON campaign_roi(user_id)")

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

    # Şehir ve sipariş saati kolonları
    _orders_new_cols = [("city", "TEXT"), ("order_hour", "INTEGER")]
    for col, dtype in _orders_new_cols:
        try:
            cur.execute(f"ALTER TABLE orders ADD COLUMN {col} {dtype}")
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

    # ── Plan sistemi ──────────────────────────────────────────────────────────
    for col_def in [("plan", "TEXT DEFAULT 'Pro'"), ("plan_period", "TEXT DEFAULT 'm'")]:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass
    cur.execute("UPDATE users SET plan = 'Pro' WHERE plan IS NULL")
    cur.execute("UPDATE users SET plan_period = 'm' WHERE plan_period IS NULL")

    # ── Şifre Sıfırlama Token'ları ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at DATETIME DEFAULT (datetime('now', '+1 hour')),
            used       INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Hedef / KPI Takibi ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            store_id  INTEGER,
            metric    TEXT NOT NULL,
            target    REAL NOT NULL DEFAULT 0,
            UNIQUE(user_id, store_id, metric),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Referral Sistemi ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id    INTEGER NOT NULL,
            referee_id     INTEGER,
            referral_code  TEXT NOT NULL UNIQUE,
            bonus_days     INTEGER DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            used_at        DATETIME,
            FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (referee_id)  REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
    except Exception:
        pass

    # ── Haftalık Rapor Takibi ─────────────────────────────────────────────────
    for col_def in [
        ("weekly_report_enabled",   "INTEGER DEFAULT 0"),
        ("weekly_report_last_sent", "DATETIME"),
    ]:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass

    # ── Stok Uyarı Sistemi (v10) ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_alerts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            store_id       INTEGER,
            product_name   TEXT NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_alerts_user ON stock_alerts(user_id)")
    except Exception:
        pass

    # ── Ürün Yorumları ve Puanları (v10) ─────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_reviews (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            store_id     INTEGER,
            product_name TEXT NOT NULL,
            rating       REAL NOT NULL,
            review_text  TEXT,
            review_date  DATE,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_reviews_user ON product_reviews(user_id)")
    except Exception:
        pass

    # ── Satıcı Skoru Takibi (v10) ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seller_scores (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER NOT NULL,
            store_id           INTEGER,
            score_date         DATE NOT NULL,
            cargo_score        REAL,
            return_score       REAL,
            satisfaction_score REAL,
            note               TEXT,
            created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_seller_scores_user ON seller_scores(user_id)")
    except Exception:
        pass

    # ── Rakip Fiyat Takibi (v10) ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS competitor_prices (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            store_id         INTEGER,
            product_name     TEXT NOT NULL,
            my_price         REAL NOT NULL DEFAULT 0,
            competitor_name  TEXT,
            competitor_price REAL NOT NULL DEFAULT 0,
            competitor_url   TEXT,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_competitor_prices_user ON competitor_prices(user_id)")
    except Exception:
        pass

    # ── Kampanya ROI (v10) ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_roi (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            store_id      INTEGER,
            campaign_name TEXT NOT NULL,
            start_date    DATE NOT NULL,
            end_date      DATE NOT NULL,
            discount_pct  REAL NOT NULL DEFAULT 0,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_campaign_roi_user ON campaign_roi(user_id)")
    except Exception:
        pass

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


# ─── Plan yönetimi ───────────────────────────────────────────────────────────

def save_user_plan(user_id: int, plan: str, plan_period: str) -> None:
    """Kullanıcının planını ve dönemini kaydeder."""
    conn = get_connection()
    conn.execute(
        "UPDATE users SET plan = ?, plan_period = ? WHERE id = ?",
        (plan, plan_period, user_id),
    )
    conn.commit()
    conn.close()


# ─── Şifre sıfırlama ─────────────────────────────────────────────────────────

def create_reset_token(email: str) -> str | None:
    """Email için tek kullanımlık şifre sıfırlama token'ı oluşturur. Email yoksa None döner."""
    import secrets as _sec
    email = email.strip().lower()
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        conn.close()
        return None
    user_id = row["id"]
    conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    token = _sec.token_urlsafe(32)
    conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token) VALUES (?, ?)",
        (user_id, token),
    )
    conn.commit()
    conn.close()
    return token


def verify_reset_token(token: str) -> dict | None:
    """Token geçerliyse kullanıcı bilgilerini döner, süresi dolmuş/kullanılmış/yoksa None."""
    if not token:
        return None
    conn = get_connection()
    row = conn.execute(
        """
        SELECT u.id, u.email
        FROM   password_reset_tokens t
        JOIN   users u ON u.id = t.user_id
        WHERE  t.token = ?
          AND  t.used  = FALSE
          AND  (t.expires_at IS NULL OR t.expires_at > datetime('now'))
        """,
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row["id"], "email": row["email"]}


def use_reset_token(token: str) -> None:
    """Token'ı kullanılmış olarak işaretler."""
    conn = get_connection()
    conn.execute("UPDATE password_reset_tokens SET used = TRUE WHERE token = ?", (token,))
    conn.commit()
    conn.close()


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
    """Yeni mağaza oluşturur; store_id döndürür.
    İlk mağaza oluşturulurken mevcut store_id=NULL siparişleri bu mağazaya bağlar."""
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM stores WHERE user_id = ?", (user_id,)).fetchone()
    is_first = (list(existing)[0] if existing else 0) == 0

    db_url = _get_db_url()
    if db_url:
        # PostgreSQL: RETURNING ile id'yi güvenilir şekilde al
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

    # Fallback: lastrowid None gelirse DB'den sorgula
    if not store_id:
        row = conn.execute(
            "SELECT id FROM stores WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        store_id = list(row.values())[0] if row else None

    # İlk mağaza: mevcut store_id=NULL siparişleri bu mağazaya bağla
    if is_first and store_id:
        conn.execute(
            "UPDATE orders SET store_id = ? WHERE user_id = ? AND store_id IS NULL",
            (store_id, user_id),
        )
        conn.execute(
            "UPDATE campaigns SET store_id = ? WHERE user_id = ? AND store_id IS NULL",
            (store_id, user_id),
        )

    conn.commit()
    conn.close()
    return store_id or 0


def link_null_orders(user_id: int, store_id: int) -> None:
    """Kullanıcıya ait store_id=NULL siparişleri belirtilen mağazaya bağlar."""
    conn = get_connection()
    conn.execute(
        "UPDATE orders SET store_id = ? WHERE user_id = ? AND store_id IS NULL",
        (store_id, user_id),
    )
    conn.execute(
        "UPDATE campaigns SET store_id = ? WHERE user_id = ? AND store_id IS NULL",
        (store_id, user_id),
    )
    conn.commit()
    conn.close()


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


def save_goals(user_id: int, store_id: int | None, goals: dict) -> None:
    """Hedefleri kaydeder (upsert)."""
    conn = get_connection()
    db_url = _get_db_url()
    for metric, target in goals.items():
        if db_url:
            conn.execute(
                "INSERT INTO goals (user_id, store_id, metric, target) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id, store_id, metric) DO UPDATE SET target = excluded.target",
                (user_id, store_id, metric, float(target)),
            )
        else:
            conn.execute(
                "INSERT INTO goals (user_id, store_id, metric, target) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id, store_id, metric) DO UPDATE SET target = excluded.target",
                (user_id, store_id, metric, float(target)),
            )
    conn.commit()
    conn.close()


def load_goals(user_id: int, store_id: int | None) -> dict:
    """Kaydedilmiş hedefleri döndürür."""
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT metric, target FROM goals WHERE user_id = ? AND store_id = ?",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT metric, target FROM goals WHERE user_id = ? AND store_id IS NULL",
            (user_id,),
        ).fetchall()
    conn.close()
    return {r["metric"]: r["target"] for r in rows}


# ─── Referral fonksiyonları ──────────────────────────────────────────────────

def get_or_create_referral_code(user_id: int) -> str:
    """Kullanıcının referral kodunu döndürür; yoksa oluşturur."""
    import secrets as _sec
    conn = get_connection()
    row = conn.execute(
        "SELECT referral_code FROM referrals WHERE referrer_id = ? AND referee_id IS NULL LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        code = row["referral_code"]
        conn.close()
        return code
    # Yeni kod oluştur
    code = "RO-" + _sec.token_urlsafe(6).upper()
    conn.execute(
        "INSERT INTO referrals (referrer_id, referral_code) VALUES (?, ?)",
        (user_id, code),
    )
    conn.commit()
    conn.close()
    return code


def use_referral_code(code: str, referee_id: int) -> dict:
    """Referral kodu kullanır. Başarılıysa {'success': True, 'bonus_days': N} döner."""
    code = code.strip().upper()
    conn = get_connection()
    # Kötüye kullanım önleme: her kullanıcı yalnızca bir kez referral kodu kullanabilir
    already = conn.execute(
        "SELECT 1 FROM referrals WHERE referee_id = ? LIMIT 1",
        (referee_id,),
    ).fetchone()
    if already:
        conn.close()
        return {"success": False, "error": "Zaten bir referral kodu kullandınız."}
    row = conn.execute(
        "SELECT id, referrer_id FROM referrals WHERE referral_code = ? AND referee_id IS NULL AND used_at IS NULL",
        (code,),
    ).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Geçersiz veya kullanılmış kod"}
    if row["referrer_id"] == referee_id:
        conn.close()
        return {"success": False, "error": "Kendi referral kodunuzu kullanamazsınız"}
    db_url = _get_db_url()
    if db_url:
        conn.execute(
            "UPDATE referrals SET referee_id = ?, bonus_days = 30, used_at = NOW() WHERE id = ?",
            (referee_id, row["id"]),
        )
    else:
        conn.execute(
            "UPDATE referrals SET referee_id = ?, bonus_days = 30, used_at = datetime('now') WHERE id = ?",
            (referee_id, row["id"]),
        )
    conn.commit()
    conn.close()
    return {"success": True, "bonus_days": 30}


def get_referral_stats(user_id: int) -> dict:
    """Kullanıcının referral istatistiklerini döndürür."""
    conn = get_connection()
    total_row = conn.execute(
        "SELECT COUNT(*) AS n FROM referrals WHERE referrer_id = ? AND referee_id IS NOT NULL",
        (user_id,),
    ).fetchone()
    bonus_row = conn.execute(
        "SELECT COALESCE(SUM(bonus_days), 0) AS n FROM referrals WHERE referrer_id = ?",
        (user_id,),
    ).fetchone()
    code_row = conn.execute(
        "SELECT referral_code FROM referrals WHERE referrer_id = ? AND referee_id IS NULL LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    total = total_row["n"] if total_row else 0
    bonus = bonus_row["n"] if bonus_row else 0
    code  = code_row["referral_code"] if code_row else None
    return {"total_referrals": int(total), "bonus_days": int(bonus), "code": code}


# ─── Haftalık rapor ──────────────────────────────────────────────────────────

def get_weekly_report_settings(user_id: int) -> dict:
    """Haftalık rapor ayarlarını döndürür."""
    conn = get_connection()
    row = conn.execute(
        "SELECT weekly_report_enabled, weekly_report_last_sent FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"enabled": False, "last_sent": None}
    return {
        "enabled":   bool(row["weekly_report_enabled"]),
        "last_sent": row["weekly_report_last_sent"],
    }


def save_weekly_report_settings(user_id: int, enabled: bool) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE users SET weekly_report_enabled = ? WHERE id = ?",
        (1 if enabled else 0, user_id),
    )
    conn.commit()
    conn.close()


def mark_weekly_report_sent(user_id: int) -> None:
    db_url = _get_db_url()
    conn = get_connection()
    if db_url:
        conn.execute(
            "UPDATE users SET weekly_report_last_sent = NOW() WHERE id = ?",
            (user_id,),
        )
    else:
        conn.execute(
            "UPDATE users SET weekly_report_last_sent = datetime('now') WHERE id = ?",
            (user_id,),
        )
    conn.commit()
    conn.close()


# ─── Stok Uyarı CRUD ────────────────────────────────────────────────────────

def save_stock_alert(user_id: int, store_id: int | None, product_name: str, stock_quantity: int) -> int:
    """Yeni stok uyarısı kaydeder; id döndürür."""
    conn = get_connection()
    db_url = _get_db_url()
    if db_url:
        cur = conn.execute(
            "INSERT INTO stock_alerts (user_id, store_id, product_name, stock_quantity) VALUES (?,?,?,?) RETURNING id",
            (user_id, store_id, product_name.strip(), int(stock_quantity)),
        )
        row_id = cur.lastrowid
    else:
        cur = conn.execute(
            "INSERT INTO stock_alerts (user_id, store_id, product_name, stock_quantity) VALUES (?,?,?,?)",
            (user_id, store_id, product_name.strip(), int(stock_quantity)),
        )
        row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_stock_alerts(user_id: int, store_id: int | None = None) -> list[dict]:
    """Kullanıcıya ait stok uyarılarını döndürür."""
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM stock_alerts WHERE user_id = ? AND store_id = ? ORDER BY created_at DESC",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM stock_alerts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_stock_alert(alert_id: int, user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM stock_alerts WHERE id = ? AND user_id = ?", (alert_id, user_id))
    conn.commit()
    conn.close()


# ─── Ürün Yorum CRUD ─────────────────────────────────────────────────────────

def save_product_reviews(user_id: int, store_id: int | None, rows: list[dict]) -> int:
    """Ürün yorumlarını toplu kaydeder; eklenen satır sayısını döndürür."""
    conn = get_connection()
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO product_reviews
               (user_id, store_id, product_name, rating, review_text, review_date)
               VALUES (?,?,?,?,?,?)""",
            (
                user_id,
                store_id,
                str(r.get("product_name", "")).strip(),
                float(r.get("rating", 0)),
                str(r.get("review_text", "")).strip(),
                r.get("review_date") or None,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_product_reviews(user_id: int, store_id: int | None = None) -> list[dict]:
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM product_reviews WHERE user_id = ? AND store_id = ? ORDER BY review_date DESC",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM product_reviews WHERE user_id = ? ORDER BY review_date DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_all_product_reviews(user_id: int, store_id: int | None = None) -> int:
    conn = get_connection()
    if store_id is not None:
        result = conn.execute(
            "DELETE FROM product_reviews WHERE user_id = ? AND store_id = ?",
            (user_id, store_id),
        )
    else:
        result = conn.execute("DELETE FROM product_reviews WHERE user_id = ?", (user_id,))
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return deleted


# ─── Satıcı Skoru CRUD ───────────────────────────────────────────────────────

def save_seller_score(
    user_id: int,
    store_id: int | None,
    score_date: str,
    cargo_score: float | None,
    return_score: float | None,
    satisfaction_score: float | None,
    note: str = "",
) -> int:
    conn = get_connection()
    db_url = _get_db_url()
    if db_url:
        cur = conn.execute(
            """INSERT INTO seller_scores
               (user_id, store_id, score_date, cargo_score, return_score, satisfaction_score, note)
               VALUES (?,?,?,?,?,?,?) RETURNING id""",
            (user_id, store_id, score_date, cargo_score, return_score, satisfaction_score, note),
        )
        row_id = cur.lastrowid
    else:
        cur = conn.execute(
            """INSERT INTO seller_scores
               (user_id, store_id, score_date, cargo_score, return_score, satisfaction_score, note)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, store_id, score_date, cargo_score, return_score, satisfaction_score, note),
        )
        row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_seller_scores(user_id: int, store_id: int | None = None) -> list[dict]:
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM seller_scores WHERE user_id = ? AND store_id = ? ORDER BY score_date",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM seller_scores WHERE user_id = ? ORDER BY score_date",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_seller_score(score_id: int, user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM seller_scores WHERE id = ? AND user_id = ?", (score_id, user_id))
    conn.commit()
    conn.close()


# ─── Rakip Fiyat CRUD ────────────────────────────────────────────────────────

def save_competitor_price(
    user_id: int,
    store_id: int | None,
    product_name: str,
    my_price: float,
    competitor_name: str,
    competitor_price: float,
    competitor_url: str = "",
) -> int:
    conn = get_connection()
    db_url = _get_db_url()
    if db_url:
        cur = conn.execute(
            """INSERT INTO competitor_prices
               (user_id, store_id, product_name, my_price, competitor_name, competitor_price, competitor_url)
               VALUES (?,?,?,?,?,?,?) RETURNING id""",
            (user_id, store_id, product_name.strip(), my_price, competitor_name.strip(), competitor_price, competitor_url.strip()),
        )
        row_id = cur.lastrowid
    else:
        cur = conn.execute(
            """INSERT INTO competitor_prices
               (user_id, store_id, product_name, my_price, competitor_name, competitor_price, competitor_url)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, store_id, product_name.strip(), my_price, competitor_name.strip(), competitor_price, competitor_url.strip()),
        )
        row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_competitor_prices(user_id: int, store_id: int | None = None) -> list[dict]:
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM competitor_prices WHERE user_id = ? AND store_id = ? ORDER BY product_name, updated_at DESC",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM competitor_prices WHERE user_id = ? ORDER BY product_name, updated_at DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_competitor_price(price_id: int, user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM competitor_prices WHERE id = ? AND user_id = ?", (price_id, user_id))
    conn.commit()
    conn.close()


# ─── Kampanya ROI CRUD ───────────────────────────────────────────────────────

def save_campaign_roi_entry(
    user_id: int,
    store_id: int | None,
    campaign_name: str,
    start_date: str,
    end_date: str,
    discount_pct: float,
) -> int:
    conn = get_connection()
    db_url = _get_db_url()
    if db_url:
        cur = conn.execute(
            """INSERT INTO campaign_roi
               (user_id, store_id, campaign_name, start_date, end_date, discount_pct)
               VALUES (?,?,?,?,?,?) RETURNING id""",
            (user_id, store_id, campaign_name.strip(), start_date, end_date, discount_pct),
        )
        row_id = cur.lastrowid
    else:
        cur = conn.execute(
            """INSERT INTO campaign_roi
               (user_id, store_id, campaign_name, start_date, end_date, discount_pct)
               VALUES (?,?,?,?,?,?)""",
            (user_id, store_id, campaign_name.strip(), start_date, end_date, discount_pct),
        )
        row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id or 0


def get_campaign_roi_entries(user_id: int, store_id: int | None = None) -> list[dict]:
    conn = get_connection()
    if store_id is not None:
        rows = conn.execute(
            "SELECT * FROM campaign_roi WHERE user_id = ? AND store_id = ? ORDER BY start_date DESC",
            (user_id, store_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM campaign_roi WHERE user_id = ? ORDER BY start_date DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_campaign_roi_entry(entry_id: int, user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM campaign_roi WHERE id = ? AND user_id = ?", (entry_id, user_id))
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
