-- ─── users tablosu ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    store_name    TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ─── orders tablosu ──────────────────────────────────────────────────────────
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
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_orders UNIQUE (user_id, order_number, customer_identifier)
);

-- ─── user_settings tablosu ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    user_id             INTEGER PRIMARY KEY,
    trendyol_seller_id  TEXT,
    trendyol_api_key    TEXT,
    trendyol_api_secret TEXT,
    last_sync_at        TIMESTAMPTZ,
    last_sync_count     INTEGER DEFAULT 0,
    CONSTRAINT fk_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ─── İndeksler ───────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_user     ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(user_id, customer_identifier);
CREATE INDEX IF NOT EXISTS idx_orders_date     ON orders(user_id, order_date);
