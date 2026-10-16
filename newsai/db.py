"""Kết nối CSDL trung tâm PostgreSQL + tiện ích ghi nhật ký ETL."""
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2

from .config import DB, SQL_DIR


def get_conn():
    return psycopg2.connect(**DB)


@contextmanager
def connection():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Chạy các file SQL trong thư mục sql/ theo thứ tự tên (tạo schema, view, user Superset)."""
    with connection() as conn, conn.cursor() as cur:
        for f in sorted(SQL_DIR.glob("*.sql")):
            print(f"  - Chạy {f.name}")
            cur.execute(f.read_text(encoding="utf-8"))


class RunLog:
    """Ghi 1 dòng vào etl.etl_run_log cho mỗi job: running -> success/failed."""

    def __init__(self, conn, job_name):
        self.conn, self.job_name = conn, job_name
        self.extracted = self.loaded = self.skipped = 0
        self.run_id = None

    def __enter__(self):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO etl.etl_run_log (job_name) VALUES (%s) RETURNING run_id",
                        (self.job_name,))
            self.run_id = cur.fetchone()[0]
        self.conn.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        status = "failed" if exc_type else "success"
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE etl.etl_run_log
                   SET finished_at = %s, status = %s, rows_extracted = %s,
                       rows_loaded = %s, rows_skipped = %s, error_message = %s
                   WHERE run_id = %s""",
                (datetime.now(timezone.utc), status, self.extracted, self.loaded,
                 self.skipped, str(exc)[:2000] if exc else None, self.run_id))
        self.conn.commit()
        return False  # không nuốt lỗi
