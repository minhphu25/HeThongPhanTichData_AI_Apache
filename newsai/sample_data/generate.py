"""Sinh DỮ LIỆU GIẢ LẬP cho các hệ thống nguồn của Hệ thống Tin tức.

Tạo ra:
  1. data/sources/cms_toasoan.db   - CSDL SQLite mô phỏng CMS của tòa soạn (bài viết, chuyên mục, tác giả)
  2. data/sources/rss/*.xml         - RSS 2.0 của 3 báo đối tác (tên chuyên mục khác nhau, HTML bẩn, tin trùng)
  3. data/labeled/sentiment_corpus.csv          - bộ dữ liệu ĐÃ GÁN NHÃN để huấn luyện mô hình AI
  4. data/labeled/production_sample_labels.csv  - nhãn đúng của 400 bài thực tế (kiểm định sau triển khai)

Toàn bộ nội dung là giả lập, KHÔNG phải tin tức thật. Chạy:  python -m newsai.sample_data.generate
"""
import csv
import hashlib
import random
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from ..config import CMS_DB_PATH, GROUND_TRUTH, LABELED_CORPUS, RSS_DIR
from .phrases import (AUTHORS, CATEGORIES, CONTEXT_SENTENCES, PLACES, RSS_CATEGORY_NAMES, RSS_DOMAINS,
                      RSS_TITLES, TONE_SENTENCES)

VN_TZ = timezone(timedelta(hours=7))
LABELS = ["positive", "neutral", "negative"]
OPPOSITE = {"positive": "negative", "negative": "positive", "neutral": None}

START, END = date(2026, 4, 1), date(2026, 10, 15)

# Tỷ lệ (tích cực, trung tính, tiêu cực) nền của từng chuyên mục
BASE_DIST = {
    "kinh-te": (0.36, 0.36, 0.28), "cong-nghe": (0.42, 0.36, 0.22), "the-thao": (0.44, 0.26, 0.30),
    "giao-duc": (0.38, 0.37, 0.25), "suc-khoe": (0.32, 0.36, 0.32), "xa-hoi": (0.28, 0.38, 0.34),
}
# Các "sự kiện" giả lập làm cảm xúc thay đổi theo thời gian (để dashboard có xu hướng rõ)
EVENTS = [
    ("kinh-te", date(2026, 8, 5), date(2026, 8, 31), "negative", 0.28),   # biến động thị trường
    ("suc-khoe", date(2026, 7, 10), date(2026, 8, 20), "negative", 0.22),  # mùa dịch sốt xuất huyết
    ("the-thao", date(2026, 9, 1), date(2026, 9, 20), "positive", 0.28),   # giải đấu khu vực
    ("xa-hoi", date(2026, 9, 25), date(2026, 10, 12), "negative", 0.30),   # bão lũ miền Trung
    ("cong-nghe", date(2026, 6, 1), date(2026, 6, 25), "positive", 0.18),  # mùa ra mắt sản phẩm
]
CATEGORY_WEIGHTS = {"kinh-te": 0.22, "cong-nghe": 0.16, "the-thao": 0.17, "giao-duc": 0.12,
                    "suc-khoe": 0.13, "xa-hoi": 0.20}


def slugify(text):
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return "-".join("".join(ch if ch.isalnum() else " " for ch in text).split())[:80]


def label_dist(cat, d):
    p = dict(zip(LABELS, BASE_DIST[cat]))
    for ecat, s, e, lab, boost in EVENTS:
        if ecat == cat and s <= d <= e:
            p[lab] += boost
    total = sum(p.values())
    return [p[k] / total for k in LABELS]


def predicate_pool(cat, label, seen_only):
    pool = CATEGORIES[cat][label]
    # Bộ huấn luyện KHÔNG chứa 2 cách diễn đạt cuối của mỗi nhóm -> kiểm định trên dữ liệu thật
    # sẽ có những cách diễn đạt mô hình chưa từng thấy (đánh giá khả năng tổng quát hóa trung thực hơn).
    return pool[:-2] if seen_only else pool


def make_text(rng, cat, label, d, seen_only=False):
    c = CATEGORIES[cat]
    subject = rng.choice(c["subjects"])
    title = f"{subject} {rng.choice(predicate_pool(cat, label, seen_only))}"
    tone = rng.choice(TONE_SENTENCES[label]).format(domain=c["domain"])
    ctx = rng.choice(CONTEXT_SENTENCES).format(place=rng.choice(PLACES), day=d.day, month=d.month)
    parts = [ctx, tone]
    # Câu "hỗn hợp": thêm ý trái chiều (nhãn vẫn theo ý chính) -> dữ liệu khó hơn, sát thực tế
    if OPPOSITE[label] and rng.random() < 0.22:
        s = rng.choice(TONE_SENTENCES[OPPOSITE[label]]).format(domain=c["domain"])
        parts.append("Tuy nhiên, " + s[0].lower() + s[1:])
    elif label == "neutral" and rng.random() < 0.15:
        parts.append(rng.choice(TONE_SENTENCES[rng.choice(["positive", "negative"])]).format(domain=c["domain"]))
    summary = " ".join(parts)
    body = summary + " " + " ".join(rng.sample(TONE_SENTENCES["neutral"], 2))
    return title, summary, body


# ---------------------------------------------------------------------------
def build_labeled_corpus(n=3000, noise=0.06, seed=7):
    rng = random.Random(seed)
    rows = []
    cats = list(CATEGORIES)
    for i in range(n):
        cat = rng.choice(cats)
        label = rng.choice(LABELS)
        d = START + timedelta(days=rng.randrange((END - START).days))
        title, summary, _ = make_text(rng, cat, label, d, seen_only=True)
        final = label
        if rng.random() < noise:  # mô phỏng bất đồng giữa người gán nhãn
            final = rng.choice([x for x in LABELS if x != label])
        rows.append({"text_id": i + 1, "category": cat, "title": title, "summary": summary, "label": final})
    LABELED_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELED_CORPUS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def build_production_articles(seed=42):
    rng = random.Random(seed)
    articles = []
    d = START
    while d <= END:
        n = rng.randint(13, 19) if d.weekday() < 5 else rng.randint(8, 12)
        for _ in range(n):
            cat = rng.choices(list(CATEGORY_WEIGHTS), weights=list(CATEGORY_WEIGHTS.values()))[0]
            label = rng.choices(LABELS, weights=label_dist(cat, d))[0]
            title, summary, body = make_text(rng, cat, label, d)
            ts = datetime(d.year, d.month, d.day, rng.randint(6, 22), rng.randint(0, 59), tzinfo=VN_TZ)
            articles.append({"cat": cat, "label": label, "title": title, "summary": summary,
                             "body": body, "published_at": ts})
        d += timedelta(days=1)
    rng.shuffle(articles)
    return articles, rng


def write_cms(articles, rng):
    CMS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CMS_DB_PATH.exists():
        CMS_DB_PATH.unlink()
    con = sqlite3.connect(CMS_DB_PATH)
    con.executescript("""
        CREATE TABLE categories (id INTEGER PRIMARY KEY, slug TEXT, name TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, full_name TEXT);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, title TEXT, sapo TEXT, body TEXT, slug TEXT,
            category_id INTEGER REFERENCES categories(id), author_id INTEGER REFERENCES authors(id),
            status TEXT, published_at TEXT, updated_at TEXT);
    """)
    cat_ids = {slug: i + 1 for i, slug in enumerate(CATEGORIES)}
    con.executemany("INSERT INTO categories VALUES (?,?,?)",
                    [(i, s, CATEGORIES[s]["name"]) for s, i in cat_ids.items()])
    con.executemany("INSERT INTO authors VALUES (?,?)", [(i + 1, a) for i, a in enumerate(AUTHORS)])
    truth = []
    for i, a in enumerate(articles, start=1001):
        status = "draft" if rng.random() < 0.03 else "published"
        updated = a["published_at"]
        title = a["title"]
        if rng.random() < 0.05:  # bài được biên tập lại sau khi đăng
            updated = a["published_at"] + timedelta(hours=rng.randint(1, 30))
            title = title + " (cập nhật)"
        con.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (i, title, a["summary"], a["body"], slugify(title), cat_ids[a["cat"]],
                     rng.randint(1, len(AUTHORS)), status, a["published_at"].isoformat(), updated.isoformat()))
        if status == "published":
            truth.append(("cms_noibo", str(i), a["label"]))
    con.commit()
    con.close()
    return truth


def write_rss(articles, rng):
    RSS_DIR.mkdir(parents=True, exist_ok=True)
    feeds = {code: [] for code in RSS_TITLES}
    truth = []
    codes = list(RSS_TITLES)
    for a in articles:
        code = rng.choice(codes)
        targets = [code]
        if rng.random() < 0.04:  # tin được nhiều báo đăng lại -> cần khử trùng lặp liên nguồn
            targets.append(rng.choice([c for c in codes if c != code]))
        for t in targets:
            guid = hashlib.md5(f"{t}|{a['title']}|{a['published_at'].isoformat()}|{a['summary']}".encode()).hexdigest()[:12]
            feeds[t].append((guid, a))
            truth.append((t, guid, a["label"]))
    for code, items in feeds.items():
        items.sort(key=lambda x: x[1]["published_at"], reverse=True)
        out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
               f"<title>{escape(RSS_TITLES[code])}</title>", f"<link>https://{RSS_DOMAINS[code]}</link>",
               "<language>vi</language>"]
        for guid, a in items:
            cat_name = RSS_CATEGORY_NAMES[code][a["cat"]]
            cat_tag = "" if rng.random() < 0.02 else f"<category>{escape(cat_name)}</category>"
            # Mô tả có HTML + khoảng trắng thừa, giống RSS thật
            desc = f'<p>  {a["summary"]}  </p><img src="https://{RSS_DOMAINS[code]}/img/{guid}.jpg" />'
            out.append(
                "<item>"
                f"<title>{escape('  ' + a['title'] + ' ')}</title>"
                f"<link>https://{RSS_DOMAINS[code]}/{slugify(a['title'])}-{guid}.html</link>"
                f"<guid isPermaLink=\"false\">{guid}</guid>"
                f"<description><![CDATA[{desc}]]></description>"
                f"{cat_tag}<pubDate>{format_datetime(a['published_at'])}</pubDate>"
                "</item>")
        out.append("</channel></rss>")
        (RSS_DIR / f"{code}.xml").write_text("\n".join(out), encoding="utf-8")
    return truth, {k: len(v) for k, v in feeds.items()}


def main():
    print("Sinh bộ dữ liệu gán nhãn ...")
    n_lab = build_labeled_corpus()
    print(f"  -> {n_lab} mẫu: {LABELED_CORPUS}")
    articles, rng = build_production_articles()
    split = int(len(articles) * 0.55)
    truth = write_cms(articles[:split], rng)
    rss_truth, feed_sizes = write_rss(articles[split:], rng)
    truth += rss_truth
    print(f"  -> CMS tòa soạn: {split} bài ({CMS_DB_PATH.name})")
    for k, v in feed_sizes.items():
        print(f"  -> RSS {k}: {v} bài")
    sample = random.Random(99).sample(truth, 400)
    with open(GROUND_TRUTH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_code", "external_id", "true_label"])
        w.writerows(sample)
    print(f"  -> Nhãn kiểm định 400 bài thực tế: {GROUND_TRUTH}")


if __name__ == "__main__":
    main()
