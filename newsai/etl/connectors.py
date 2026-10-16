"""CONNECTOR: lớp kết nối tới từng hệ thống nguồn của Hệ thống Tin tức.

Mỗi connector trả về các bản ghi thống nhất dạng:
    {"source_record_id": str, "event_time": datetime (có múi giờ), "payload": dict}
-> thêm nguồn mới (vd: API mạng xã hội) chỉ cần viết thêm 1 class có hàm extract(since).
"""
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))


class BaseConnector:
    source_code = None
    source_type = None

    def extract(self, since=None):
        raise NotImplementedError


class CMSConnector(BaseConnector):
    """Đọc trực tiếp CSDL của CMS tòa soạn, chỉ lấy bài đã xuất bản và có updated_at > watermark.

    Bản demo dùng SQLite. Khi CMS thật chạy MySQL/PostgreSQL: thay sqlite3.connect bằng driver tương ứng,
    câu SQL giữ nguyên (nên dùng tài khoản chỉ đọc hoặc bản sao read-replica để không ảnh hưởng tòa soạn).
    """
    source_code = "cms_noibo"
    source_type = "CMS"

    QUERY = """
        SELECT a.id, a.title, a.sapo, a.body, a.slug, c.slug AS category, au.full_name AS author,
               a.published_at, a.updated_at
        FROM articles a
        JOIN categories c ON c.id = a.category_id
        LEFT JOIN authors au ON au.id = a.author_id
        WHERE a.status = 'published' AND a.updated_at >= ?  -- '>=': an toàn khi trùng mốc, bản ghi trùng bị loại ở staging
        ORDER BY a.updated_at
    """

    def __init__(self, db_path, base_url="https://toasoan.example"):
        self.db_path, self.base_url = Path(db_path), base_url

    def extract(self, since=None):
        since_str = (since or datetime(1970, 1, 1, tzinfo=timezone.utc)).astimezone(VN_TZ).isoformat()
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            for row in con.execute(self.QUERY, (since_str,)):
                rec = dict(row)
                rec["url"] = f"{self.base_url}/{rec['slug']}-{rec['id']}.html"
                yield {"source_record_id": str(rec["id"]),
                       "event_time": datetime.fromisoformat(rec["updated_at"]),
                       "payload": rec}
        finally:
            con.close()


class RSSConnector(BaseConnector):
    """Đọc RSS 2.0 của báo đối tác. `location` là URL (http/https) hoặc đường dẫn file."""
    source_type = "RSS"

    # Báo đối tác có thể đăng bài với pubDate lùi giờ -> lùi mốc 6 giờ để không bỏ sót;
    # bản ghi lấy lại sẽ bị loại trùng ở staging (UNIQUE source_code + id + hash).
    LOOKBACK = timedelta(hours=6)

    def __init__(self, source_code, location, timeout=20):
        self.source_code, self.location, self.timeout = source_code, location, timeout

    def _read(self):
        if str(self.location).startswith(("http://", "https://")):
            req = urllib.request.Request(self.location, headers={"User-Agent": "NewsAI-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        return Path(self.location).read_bytes()

    def extract(self, since=None):
        since = since - self.LOOKBACK if since else None
        root = ET.fromstring(self._read())
        for item in root.iter("item"):
            pub = item.findtext("pubDate")
            try:
                event_time = parsedate_to_datetime(pub) if pub else None
            except (TypeError, ValueError):
                event_time = None
            if event_time is None:
                continue  # bản ghi lỗi ngày -> bỏ qua ở bước extract
            if since and event_time < since:
                continue
            guid = item.findtext("guid") or item.findtext("link")
            yield {"source_record_id": guid.strip(),
                   "event_time": event_time,
                   "payload": {"guid": guid.strip(), "title": item.findtext("title"),
                               "link": item.findtext("link"), "description": item.findtext("description"),
                               "category": item.findtext("category"), "pub_date": event_time.isoformat()}}
