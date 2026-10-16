"""Mô phỏng tin MỚI phát sinh ở hệ thống nguồn để demo nạp tăng dần (incremental load):
  - thêm N bài mới vào CMS tòa soạn + biên tập lại 1 bài cũ
  - thêm N bài mới vào RSS của Tin Nhanh 24h
Sau đó chạy:  python -m newsai.run_all --steps etl predict forecast
"""
import argparse
import hashlib
import random
import re
import sqlite3
from datetime import datetime, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape

from ..config import CMS_DB_PATH, RSS_DIR
from .generate import LABELS, VN_TZ, make_text, slugify
from .phrases import CATEGORIES, RSS_CATEGORY_NAMES


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=5, help="số bài mới mỗi nguồn")
    args = ap.parse_args(argv)
    rng = random.Random()
    now = datetime.now(VN_TZ).replace(microsecond=0)
    cats = list(CATEGORIES)

    con = sqlite3.connect(CMS_DB_PATH)
    cat_ids = dict(con.execute("SELECT slug, id FROM categories"))
    next_id = con.execute("SELECT MAX(id) FROM articles").fetchone()[0] + 1
    for i in range(args.n):
        cat, label = rng.choice(cats), rng.choice(LABELS)
        ts = now - timedelta(minutes=rng.randint(1, 120))
        title, summary, body = make_text(rng, cat, label, ts.date())
        con.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (next_id + i, title, summary, body, slugify(title), cat_ids[cat], rng.randint(1, 10),
                     "published", ts.isoformat(), now.isoformat()))  # CMS ghi updated_at = thời điểm lưu
    old_id = con.execute("SELECT id FROM articles WHERE status='published' ORDER BY RANDOM() LIMIT 1").fetchone()[0]
    con.execute("UPDATE articles SET title = title || ' (cập nhật)', updated_at = ? WHERE id = ?",
                (now.isoformat(), old_id))
    con.commit()
    con.close()
    print(f"CMS: thêm {args.n} bài mới (id {next_id}..{next_id + args.n - 1}), biên tập lại bài id {old_id}")

    path = RSS_DIR / "tinnhanh24h.xml"
    xml = path.read_text(encoding="utf-8")
    items = []
    for _ in range(args.n):
        cat, label = rng.choice(cats), rng.choice(LABELS)
        ts = now - timedelta(minutes=rng.randint(1, 120))
        title, summary, _ = make_text(rng, cat, label, ts.date())
        guid = hashlib.md5(f"tinnhanh24h|{title}|{ts.isoformat()}|{summary}".encode()).hexdigest()[:12]
        items.append(f"<item><title>{escape(title)}</title>"
                     f"<link>https://tinnhanh24h.example/{slugify(title)}-{guid}.html</link>"
                     f"<guid isPermaLink=\"false\">{guid}</guid>"
                     f"<description><![CDATA[<p>{summary}</p>]]></description>"
                     f"<category>{escape(RSS_CATEGORY_NAMES['tinnhanh24h'][cat])}</category>"
                     f"<pubDate>{format_datetime(ts)}</pubDate></item>")
    xml = re.sub(r"(<language>vi</language>)", lambda m: m.group(1) + "\n" + "\n".join(items), xml, count=1)
    path.write_text(xml, encoding="utf-8")
    print(f"RSS tinnhanh24h: thêm {args.n} bài mới")


if __name__ == "__main__":
    main()
