"""Cấu hình chung - đọc từ biến môi trường (hoặc file .env) để không ghi cứng mật khẩu vào code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DB = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DB", "news_dw"),
    "user": os.getenv("PG_USER", "news_admin"),
    "password": os.getenv("PG_PASSWORD", "news_admin_123"),
}

DATA_DIR = ROOT / "data"
SOURCE_DIR = DATA_DIR / "sources"                 # dữ liệu giả lập các hệ thống nguồn
CMS_DB_PATH = SOURCE_DIR / "cms_toasoan.db"       # CSDL của CMS tòa soạn (SQLite)
RSS_DIR = SOURCE_DIR / "rss"                      # RSS feed của các báo đối tác
LABELED_CORPUS = DATA_DIR / "labeled" / "sentiment_corpus.csv"
GROUND_TRUTH = DATA_DIR / "labeled" / "production_sample_labels.csv"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
SQL_DIR = ROOT / "sql"

# Danh sách RSS: khi chạy thật thay đường dẫn file bằng URL (http/https) của báo
RSS_FEEDS = {
    "tinnhanh24h": os.getenv("RSS_TINNHANH24H", str(RSS_DIR / "tinnhanh24h.xml")),
    "thoibaoso": os.getenv("RSS_THOIBAOSO", str(RSS_DIR / "thoibaoso.xml")),
    "nhipsongviet": os.getenv("RSS_NHIPSONGVIET", str(RSS_DIR / "nhipsongviet.xml")),
}

TIMEZONE = "Asia/Ho_Chi_Minh"
