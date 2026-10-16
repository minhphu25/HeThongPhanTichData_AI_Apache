-- =====================================================================
--  CƠ SỞ DỮ LIỆU TRUNG TÂM: news_dw (PostgreSQL 14+)
--  Hệ thống Phân tích Tin tức tích hợp AI - Phần 1: Kiến trúc dữ liệu
--
--  Kiến trúc 4 tầng (schema):
--    etl       : điều phối ETL (watermark, nhật ký chạy, bảng ánh xạ)
--    staging   : dữ liệu thô nguyên bản từ nguồn (JSONB), chỉ ghi thêm
--    core      : dữ liệu đã làm sạch, chuẩn hóa, khử trùng lặp
--    analytics : kết quả mô hình AI + view phục vụ Apache Superset
--  Chạy lại nhiều lần được (idempotent).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------
-- 1. Tầng ETL: điều phối và giám sát
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl.etl_run_log (
    run_id          BIGSERIAL PRIMARY KEY,
    job_name        TEXT        NOT NULL,              -- vd: extract:cms_noibo, transform, ai:predict
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'failed')),
    rows_extracted  INTEGER     DEFAULT 0,
    rows_loaded     INTEGER     DEFAULT 0,
    rows_skipped    INTEGER     DEFAULT 0,
    error_message   TEXT
);

-- Mốc dữ liệu đã nạp của từng nguồn -> phục vụ nạp tăng dần (incremental load)
CREATE TABLE IF NOT EXISTS etl.watermark (
    source_code     TEXT PRIMARY KEY,
    last_value      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ánh xạ chuyên mục của từng nguồn về chuyên mục chuẩn
CREATE TABLE IF NOT EXISTS etl.category_map (
    source_code     TEXT NOT NULL,
    source_category TEXT NOT NULL,                     -- giá trị đã chuẩn hóa chữ thường
    category_code   TEXT NOT NULL,
    PRIMARY KEY (source_code, source_category)
);

-- ---------------------------------------------------------------------
-- 2. Tầng STAGING: lưu nguyên bản bản ghi nguồn (phục vụ truy vết, nạp lại)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.raw_article (
    raw_id          BIGSERIAL PRIMARY KEY,
    source_code     TEXT        NOT NULL,
    source_record_id TEXT       NOT NULL,              -- id/guid ở hệ thống nguồn
    payload         JSONB       NOT NULL,              -- bản ghi gốc
    record_hash     CHAR(32)    NOT NULL,              -- md5 payload -> phát hiện bản ghi đổi nội dung
    run_id          BIGINT      REFERENCES etl.etl_run_log(run_id),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed       BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (source_code, source_record_id, record_hash)
);
CREATE INDEX IF NOT EXISTS ix_raw_article_unprocessed
    ON staging.raw_article (processed) WHERE processed = FALSE;

-- ---------------------------------------------------------------------
-- 3. Tầng CORE: mô hình dữ liệu chuẩn hóa (dạng sao: dim + bảng sự kiện)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.dim_source (
    source_id       SERIAL PRIMARY KEY,
    source_code     TEXT UNIQUE NOT NULL,
    source_name     TEXT NOT NULL,
    source_type     TEXT NOT NULL CHECK (source_type IN ('CMS', 'RSS', 'API')),
    base_url        TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS core.dim_category (
    category_id     SERIAL PRIMARY KEY,
    category_code   TEXT UNIQUE NOT NULL,
    category_name   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_date (
    date_key        DATE PRIMARY KEY,
    day_of_month    SMALLINT,
    month           SMALLINT,
    quarter         SMALLINT,
    year            SMALLINT,
    iso_week        SMALLINT,
    day_of_week     SMALLINT,                          -- 1 = Thứ Hai ... 7 = Chủ Nhật
    day_name_vi     TEXT,
    is_weekend      BOOLEAN
);

CREATE TABLE IF NOT EXISTS core.article (
    article_id      BIGSERIAL PRIMARY KEY,
    source_id       INTEGER     NOT NULL REFERENCES core.dim_source(source_id),
    external_id     TEXT        NOT NULL,              -- id của bài ở hệ thống nguồn
    category_id     INTEGER     REFERENCES core.dim_category(category_id),
    title           TEXT        NOT NULL,
    summary         TEXT,
    content         TEXT,
    url             TEXT,
    author          TEXT,
    published_at    TIMESTAMPTZ NOT NULL,
    published_date  DATE        NOT NULL,
    word_count      INTEGER,
    content_hash    CHAR(32)    NOT NULL,              -- md5(tiêu đề + tóm tắt chuẩn hóa) -> khử trùng lặp liên nguồn
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS ix_article_published ON core.article (published_at);
CREATE INDEX IF NOT EXISTS ix_article_hash      ON core.article (content_hash);
CREATE INDEX IF NOT EXISTS ix_article_category  ON core.article (category_id);

-- ---------------------------------------------------------------------
-- 4. Tầng ANALYTICS: kết quả AI (Phần 2) - nguồn dữ liệu cho Superset
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.model_registry (
    model_version   TEXT PRIMARY KEY,                  -- vd: sentiment-logreg-20261016-0830
    task            TEXT NOT NULL DEFAULT 'sentiment',
    algorithm       TEXT NOT NULL,
    artifact_path   TEXT NOT NULL,                     -- đường dẫn file .joblib
    trained_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    train_size      INTEGER,
    test_size       INTEGER,
    accuracy        NUMERIC(6,4),
    f1_macro        NUMERIC(6,4),
    metrics         JSONB,                             -- báo cáo đầy đủ (per-class, confusion matrix, so sánh mô hình)
    is_active       BOOLEAN NOT NULL DEFAULT FALSE
);
-- Mỗi tác vụ chỉ có tối đa 1 mô hình đang hoạt động
CREATE UNIQUE INDEX IF NOT EXISTS ux_model_active
    ON analytics.model_registry (task) WHERE is_active;

CREATE TABLE IF NOT EXISTS analytics.article_sentiment (
    article_id      BIGINT  NOT NULL REFERENCES core.article(article_id) ON DELETE CASCADE,
    model_version   TEXT    NOT NULL REFERENCES analytics.model_registry(model_version),
    label           TEXT    NOT NULL CHECK (label IN ('positive', 'neutral', 'negative')),
    prob_positive   NUMERIC(5,4),
    prob_neutral    NUMERIC(5,4),
    prob_negative   NUMERIC(5,4),
    sentiment_score NUMERIC(5,4),                      -- = P(tích cực) - P(tiêu cực), thang [-1, 1]
    confidence      NUMERIC(5,4),                      -- = xác suất lớn nhất
    content_hash    CHAR(32),                          -- hash lúc chấm điểm -> chấm lại nếu bài bị sửa
    predicted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, model_version)
);

CREATE TABLE IF NOT EXISTS analytics.article_keyword (
    article_id      BIGINT  NOT NULL REFERENCES core.article(article_id) ON DELETE CASCADE,
    keyword         TEXT    NOT NULL,
    weight          NUMERIC(6,4),
    rank            SMALLINT,
    PRIMARY KEY (article_id, keyword)
);

CREATE TABLE IF NOT EXISTS analytics.sentiment_forecast (
    category_code   TEXT    NOT NULL,                  -- 'all' = toàn hệ thống
    forecast_date   DATE    NOT NULL,
    predicted_index NUMERIC(6,4),
    lower_bound     NUMERIC(6,4),
    upper_bound     NUMERIC(6,4),
    model_version   TEXT    NOT NULL,
    backtest_mae    NUMERIC(6,4),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (category_code, forecast_date)
);

-- ---------------------------------------------------------------------
-- 5. Dữ liệu danh mục ban đầu
-- ---------------------------------------------------------------------
INSERT INTO core.dim_category (category_code, category_name) VALUES
    ('kinh-te',   'Kinh tế'),
    ('cong-nghe', 'Công nghệ'),
    ('the-thao',  'Thể thao'),
    ('giao-duc',  'Giáo dục'),
    ('suc-khoe',  'Sức khỏe'),
    ('xa-hoi',    'Thời sự - Xã hội'),
    ('khac',      'Khác')
ON CONFLICT (category_code) DO NOTHING;

INSERT INTO core.dim_source (source_code, source_name, source_type, base_url) VALUES
    ('cms_noibo',    'CMS Tòa soạn (nội bộ)', 'CMS', NULL),
    ('tinnhanh24h',  'Tin Nhanh 24h',         'RSS', 'https://tinnhanh24h.example/rss'),
    ('thoibaoso',    'Thời Báo Số',           'RSS', 'https://thoibaoso.example/feed'),
    ('nhipsongviet', 'Nhịp Sống Việt',        'RSS', 'https://nhipsongviet.example/rss')
ON CONFLICT (source_code) DO NOTHING;

INSERT INTO etl.category_map (source_code, source_category, category_code) VALUES
    -- CMS dùng slug chuẩn
    ('cms_noibo', 'kinh-te', 'kinh-te'), ('cms_noibo', 'cong-nghe', 'cong-nghe'),
    ('cms_noibo', 'the-thao', 'the-thao'), ('cms_noibo', 'giao-duc', 'giao-duc'),
    ('cms_noibo', 'suc-khoe', 'suc-khoe'), ('cms_noibo', 'xa-hoi', 'xa-hoi'),
    -- Các nguồn RSS đặt tên chuyên mục khác nhau
    ('tinnhanh24h', 'kinh doanh', 'kinh-te'), ('tinnhanh24h', 'số hóa', 'cong-nghe'),
    ('tinnhanh24h', 'thể thao', 'the-thao'),  ('tinnhanh24h', 'giáo dục', 'giao-duc'),
    ('tinnhanh24h', 'sức khỏe', 'suc-khoe'),  ('tinnhanh24h', 'thời sự', 'xa-hoi'),
    ('thoibaoso', 'tài chính', 'kinh-te'),    ('thoibaoso', 'công nghệ', 'cong-nghe'),
    ('thoibaoso', 'bóng đá', 'the-thao'),     ('thoibaoso', 'thể thao', 'the-thao'),
    ('thoibaoso', 'giáo dục', 'giao-duc'),    ('thoibaoso', 'y tế', 'suc-khoe'),
    ('thoibaoso', 'xã hội', 'xa-hoi'),
    ('nhipsongviet', 'kinh tế', 'kinh-te'),   ('nhipsongviet', 'khoa học - công nghệ', 'cong-nghe'),
    ('nhipsongviet', 'thể thao', 'the-thao'), ('nhipsongviet', 'giáo dục', 'giao-duc'),
    ('nhipsongviet', 'sức khỏe', 'suc-khoe'), ('nhipsongviet', 'đời sống', 'xa-hoi')
ON CONFLICT DO NOTHING;

-- Bảng ngày 2025-01-01 -> 2027-12-31
INSERT INTO core.dim_date
SELECT d::date,
       EXTRACT(DAY FROM d), EXTRACT(MONTH FROM d), EXTRACT(QUARTER FROM d), EXTRACT(YEAR FROM d),
       EXTRACT(WEEK FROM d), EXTRACT(ISODOW FROM d),
       (ARRAY['Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy','Chủ Nhật'])[EXTRACT(ISODOW FROM d)::int],
       EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series('2025-01-01'::date, '2027-12-31'::date, interval '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;
