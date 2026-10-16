"""PIPELINE ETL: Nguồn -> staging -> core (CSDL trung tâm PostgreSQL).

Bước 1 - EXTRACT & LOAD (EL): mỗi connector lấy bản ghi mới (theo watermark) và ghi NGUYÊN BẢN vào
          staging.raw_article (JSONB). Bản ghi trùng (cùng nguồn, id, nội dung) tự bị loại nhờ UNIQUE.
Bước 2 - TRANSFORM: làm sạch HTML, chuẩn hóa Unicode NFC, ánh xạ chuyên mục, kiểm tra hợp lệ,
          khử trùng lặp liên nguồn (md5 tiêu đề + tóm tắt chuẩn hóa), UPSERT vào core.article.
Mỗi bước ghi nhật ký vào etl.etl_run_log. Chạy lại nhiều lần không sinh dữ liệu trùng (idempotent).
"""
import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime

from psycopg2.extras import Json

from ..config import CMS_DB_PATH, RSS_FEEDS
from ..db import RunLog
from .connectors import CMSConnector, RSSConnector

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
UPDATE_SUFFIX_RE = re.compile(r"\s*\((cập nhật|update[d]?)\)\s*$", re.IGNORECASE)


def get_connectors():
    return [CMSConnector(CMS_DB_PATH)] + [RSSConnector(code, loc) for code, loc in RSS_FEEDS.items()]


# ----------------------------------------------------------------------------- helpers
def clean_text(text):
    """Bỏ thẻ HTML, giải mã &amp;..., chuẩn hóa Unicode tiếng Việt (NFC), gộp khoảng trắng."""
    if not text:
        return None
    text = html.unescape(TAG_RE.sub(" ", text))
    text = unicodedata.normalize("NFC", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text or None


def content_hash(title, summary):
    """Khóa khử trùng lặp liên nguồn: md5(tiêu đề + 200 ký tự đầu tóm tắt), chữ thường,
    bỏ hậu tố '(cập nhật)'. Cùng một tin được nhiều báo đăng lại sẽ cho cùng khóa."""
    key = UPDATE_SUFFIX_RE.sub("", title).lower() + "|" + (summary or "")[:200].lower()
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def record_hash(payload):
    return hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# ----------------------------------------------------------------------------- bước 1: extract
def get_watermark(cur, source_code):
    cur.execute("SELECT last_value FROM etl.watermark WHERE source_code = %s", (source_code,))
    row = cur.fetchone()
    return row[0] if row else None


def extract_source(conn, connector):
    with RunLog(conn, f"extract:{connector.source_code}") as log, conn.cursor() as cur:
        since = get_watermark(cur, connector.source_code)
        max_time = since
        for rec in connector.extract(since):
            log.extracted += 1
            cur.execute(
                """INSERT INTO staging.raw_article (source_code, source_record_id, payload, record_hash, run_id)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (source_code, source_record_id, record_hash) DO NOTHING""",
                (connector.source_code, rec["source_record_id"], Json(rec["payload"]),
                 record_hash(rec["payload"]), log.run_id))
            if cur.rowcount == 1:
                log.loaded += 1
            else:
                log.skipped += 1
            if max_time is None or rec["event_time"] > max_time:
                max_time = rec["event_time"]
        if max_time is not None:
            cur.execute(
                """INSERT INTO etl.watermark (source_code, last_value) VALUES (%s, %s)
                   ON CONFLICT (source_code) DO UPDATE SET last_value = EXCLUDED.last_value, updated_at = now()""",
                (connector.source_code, max_time))
        conn.commit()
        print(f"  [extract] {connector.source_code:<13} mốc từ: {since}  "
              f"-> lấy {log.extracted}, nạp mới {log.loaded}, trùng {log.skipped}")
        return log.loaded


# ----------------------------------------------------------------------------- bước 2: transform
def normalize(source_code, source_type, p):
    """Đưa payload của từng loại nguồn về cùng 1 cấu trúc."""
    if source_type == "CMS":
        return {"external_id": str(p["id"]), "title": clean_text(p.get("title")),
                "summary": clean_text(p.get("sapo")), "content": clean_text(p.get("body")),
                "url": p.get("url"), "author": p.get("author"), "category": p.get("category"),
                "published_at": p.get("published_at")}
    # RSS
    return {"external_id": p["guid"], "title": clean_text(p.get("title")),
            "summary": clean_text(p.get("description")), "content": None,
            "url": (p.get("link") or "").strip() or None, "author": None,
            "category": p.get("category"), "published_at": p.get("pub_date")}


def transform(conn):
    with RunLog(conn, "transform:staging->core") as log, conn.cursor() as cur:
        cur.execute("SELECT source_code, source_id, source_type FROM core.dim_source")
        sources = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        cur.execute("SELECT category_code, category_id FROM core.dim_category")
        categories = dict(cur.fetchall())
        cur.execute("SELECT source_code, source_category, category_code FROM etl.category_map")
        cat_map = {(r[0], r[1]): r[2] for r in cur.fetchall()}

        cur.execute("""SELECT raw_id, source_code, payload FROM staging.raw_article
                       WHERE NOT processed ORDER BY raw_id""")
        rows = cur.fetchall()
        dup = invalid = unmapped = 0
        for raw_id, source_code, payload in rows:
            log.extracted += 1
            source_id, source_type = sources[source_code]
            a = normalize(source_code, source_type, payload)

            # Kiểm tra hợp lệ
            if not a["title"] or not a["published_at"]:
                invalid += 1
                continue
            published_at = datetime.fromisoformat(a["published_at"])

            # Ánh xạ chuyên mục
            raw_cat = clean_text(a["category"]).lower() if a["category"] else ""
            cat_code = cat_map.get((source_code, raw_cat))
            if cat_code is None:
                unmapped += 1
                cat_code = "khac"

            h = content_hash(a["title"], a["summary"])
            # Khử trùng lặp liên nguồn: cùng tin đã có từ nguồn khác -> bỏ qua
            cur.execute("SELECT 1 FROM core.article WHERE content_hash = %s AND source_id <> %s LIMIT 1",
                        (h, source_id))
            if cur.fetchone():
                dup += 1
                continue

            text_for_count = " ".join(filter(None, [a["title"], a["summary"], a["content"]]))
            cur.execute(
                """INSERT INTO core.article (source_id, external_id, category_id, title, summary, content, url,
                                             author, published_at, published_date, word_count, content_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, (%s AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, %s, %s)
                   ON CONFLICT (source_id, external_id) DO UPDATE
                   SET category_id = EXCLUDED.category_id, title = EXCLUDED.title, summary = EXCLUDED.summary,
                       content = EXCLUDED.content, url = EXCLUDED.url, author = EXCLUDED.author,
                       published_at = EXCLUDED.published_at, published_date = EXCLUDED.published_date,
                       word_count = EXCLUDED.word_count, content_hash = EXCLUDED.content_hash,
                       last_updated_at = now()
                   WHERE core.article.title IS DISTINCT FROM EXCLUDED.title
                      OR core.article.summary IS DISTINCT FROM EXCLUDED.summary
                      OR core.article.category_id IS DISTINCT FROM EXCLUDED.category_id""",
                (source_id, a["external_id"], categories[cat_code], a["title"], a["summary"], a["content"],
                 a["url"], a["author"], published_at, published_at, len(text_for_count.split()), h))
            log.loaded += cur.rowcount

        cur.execute("UPDATE staging.raw_article SET processed = TRUE WHERE NOT processed AND raw_id <= %s",
                    (rows[-1][0] if rows else 0,))
        log.skipped = dup + invalid
        conn.commit()
        print(f"  [transform] đọc {log.extracted} bản ghi staging -> ghi/cập nhật {log.loaded} bài, "
              f"trùng liên nguồn {dup}, không hợp lệ {invalid}, chuyên mục không ánh xạ được {unmapped}")
        return log.loaded


def run(conn):
    print("ETL: Extract & Load vào staging")
    for c in get_connectors():
        extract_source(conn, c)
    print("ETL: Transform staging -> core")
    transform(conn)
