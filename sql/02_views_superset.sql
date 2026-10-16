-- =====================================================================
--  VIEW PHỤC VỤ APACHE SUPERSET (bàn giao cho Phần 3 & 4)
--  Superset chỉ cần đọc schema "analytics" -> không phải viết JOIN phức tạp.
--  Các view luôn lấy kết quả của mô hình đang hoạt động (is_active = TRUE).
-- =====================================================================

-- 1) Chi tiết từng bài báo kèm kết quả cảm xúc (dataset chính cho Superset)
CREATE OR REPLACE VIEW analytics.v_article_sentiment AS
SELECT a.article_id,
       a.title,
       a.summary,
       a.url,
       a.author,
       a.published_at,
       a.published_date,
       EXTRACT(HOUR FROM a.published_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::int AS published_hour,
       d.day_name_vi,
       d.iso_week,
       d.month,
       s.source_code,
       s.source_name,
       s.source_type,
       c.category_code,
       c.category_name,
       a.word_count,
       se.label,
       CASE se.label WHEN 'positive' THEN 'Tích cực'
                     WHEN 'neutral'  THEN 'Trung tính'
                     WHEN 'negative' THEN 'Tiêu cực' END                     AS label_vi,
       se.sentiment_score,
       se.confidence,
       se.prob_positive, se.prob_neutral, se.prob_negative,
       se.model_version
FROM core.article a
JOIN core.dim_source   s  ON s.source_id   = a.source_id
JOIN core.dim_category c  ON c.category_id = a.category_id
JOIN core.dim_date     d  ON d.date_key    = a.published_date
JOIN analytics.article_sentiment se ON se.article_id = a.article_id
JOIN analytics.model_registry    m  ON m.model_version = se.model_version AND m.is_active;

-- 2) Tổng hợp theo ngày x chuyên mục x nguồn (biểu đồ xu hướng, stacked bar)
CREATE OR REPLACE VIEW analytics.v_daily_sentiment AS
SELECT published_date,
       category_name,
       source_name,
       COUNT(*)                                          AS total_articles,
       COUNT(*) FILTER (WHERE label = 'positive')        AS positive_count,
       COUNT(*) FILTER (WHERE label = 'neutral')         AS neutral_count,
       COUNT(*) FILTER (WHERE label = 'negative')        AS negative_count,
       ROUND(AVG(sentiment_score), 4)                    AS avg_sentiment_score,
       ROUND(COUNT(*) FILTER (WHERE label = 'negative')::numeric / COUNT(*), 4) AS negative_ratio
FROM analytics.v_article_sentiment
GROUP BY published_date, category_name, source_name;

-- 3) Chỉ số cảm xúc trung bình trượt 7 ngày theo chuyên mục (line chart)
CREATE OR REPLACE VIEW analytics.v_sentiment_index_7d AS
WITH daily AS (
    SELECT published_date, category_name,
           COUNT(*) AS n, AVG(sentiment_score) AS avg_score
    FROM analytics.v_article_sentiment
    GROUP BY published_date, category_name
)
SELECT published_date,
       category_name,
       n AS total_articles,
       ROUND(avg_score, 4) AS daily_index,
       ROUND(AVG(avg_score) OVER (PARTITION BY category_name ORDER BY published_date
                                  ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 4) AS index_7d
FROM daily;

-- 4) Từ khóa nổi bật (word cloud) theo chuyên mục và nhãn cảm xúc
CREATE OR REPLACE VIEW analytics.v_keyword_trend AS
SELECT v.published_date,
       v.category_name,
       v.label_vi,
       k.keyword,
       k.weight
FROM analytics.article_keyword k
JOIN analytics.v_article_sentiment v ON v.article_id = k.article_id;

-- 5) Thực tế + dự báo chỉ số cảm xúc (biểu đồ dự báo)
CREATE OR REPLACE VIEW analytics.v_sentiment_forecast AS
SELECT COALESCE(c.category_name, 'Toàn hệ thống') AS category_name,
       f.forecast_date AS date_key,
       'Dự báo' AS series,
       f.predicted_index AS sentiment_index,
       f.lower_bound, f.upper_bound,
       f.backtest_mae
FROM analytics.sentiment_forecast f
LEFT JOIN core.dim_category c ON c.category_code = f.category_code
UNION ALL
SELECT category_name, published_date, 'Thực tế', daily_index, NULL, NULL, NULL
FROM analytics.v_sentiment_index_7d
UNION ALL
SELECT 'Toàn hệ thống', published_date, 'Thực tế', ROUND(AVG(sentiment_score), 4), NULL, NULL, NULL
FROM analytics.v_article_sentiment
GROUP BY published_date;

-- 6) Giám sát chất lượng mô hình & ETL
CREATE OR REPLACE VIEW analytics.v_model_performance AS
SELECT model_version, algorithm, trained_at, train_size, test_size,
       accuracy, f1_macro, is_active
FROM analytics.model_registry;

CREATE OR REPLACE VIEW analytics.v_etl_monitoring AS
SELECT run_id, job_name, started_at, finished_at,
       EXTRACT(EPOCH FROM (finished_at - started_at))::numeric(10,2) AS duration_sec,
       status, rows_extracted, rows_loaded, rows_skipped, error_message
FROM etl.etl_run_log;
