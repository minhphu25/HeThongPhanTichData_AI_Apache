-- =====================================================================
--  Tài khoản CHỈ ĐỌC cho Apache Superset (nguyên tắc quyền tối thiểu)
--  Chạy bằng tài khoản quản trị (news_admin). Nhớ đổi mật khẩu khi triển khai thật.
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
        CREATE ROLE superset_reader LOGIN PASSWORD 'superset_reader_123';
    END IF;
END $$;

GRANT CONNECT ON DATABASE news_dw TO superset_reader;
GRANT USAGE ON SCHEMA analytics, core TO superset_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO superset_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO superset_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO superset_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA core      GRANT SELECT ON TABLES TO superset_reader;
-- Superset cần đọc view analytics.v_etl_monitoring (đọc etl.etl_run_log)
GRANT USAGE ON SCHEMA etl TO superset_reader;
GRANT SELECT ON etl.etl_run_log TO superset_reader;
