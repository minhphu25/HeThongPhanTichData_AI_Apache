"""PHẦN 2 - TRIỂN KHAI MÔ HÌNH: chấm điểm cảm xúc + trích xuất từ khóa cho bài báo trong core.article,
ghi kết quả vào schema analytics để Superset hiển thị.

- Chỉ chấm các bài CHƯA có kết quả của mô hình đang hoạt động, hoặc bài đã bị sửa nội dung
  (content_hash thay đổi) -> chạy định kỳ (vd: mỗi 15 phút) rất nhẹ.
- sentiment_score = P(tích cực) - P(tiêu cực) thuộc [-1, 1] -> dễ vẽ chỉ số cảm xúc theo thời gian.
"""
import joblib
import numpy as np
from psycopg2.extras import execute_values
from sklearn.feature_extraction.text import TfidfVectorizer

from ..db import RunLog
from .text import build_input, keyword_analyzer

BATCH = 500
TOP_K_KEYWORDS = 5


def load_active_model(cur):
    cur.execute("""SELECT model_version, artifact_path FROM analytics.model_registry
                   WHERE task = 'sentiment' AND is_active""")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Chưa có mô hình nào được kích hoạt. Hãy chạy bước huấn luyện trước.")
    bundle = joblib.load(row[1])
    return row[0], bundle["model"]


def predict_sentiment(conn):
    with RunLog(conn, "ai:predict_sentiment") as log, conn.cursor() as cur:
        version, model = load_active_model(cur)
        cur.execute(
            """SELECT a.article_id, a.title, a.summary, a.content_hash
               FROM core.article a
               LEFT JOIN analytics.article_sentiment s
                      ON s.article_id = a.article_id AND s.model_version = %s
               WHERE s.article_id IS NULL OR s.content_hash IS DISTINCT FROM a.content_hash
               ORDER BY a.article_id""", (version,))
        rows = cur.fetchall()
        log.extracted = len(rows)
        classes = list(model.classes_)
        idx = {c: classes.index(c) for c in ("positive", "neutral", "negative")}
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            proba = model.predict_proba([build_input(r[1], r[2]) for r in chunk])
            values = []
            for r, p in zip(chunk, proba):
                pp, pn, pg = (float(p[idx["positive"]]), float(p[idx["neutral"]]), float(p[idx["negative"]]))
                label = classes[int(np.argmax(p))]
                values.append((r[0], version, label, round(pp, 4), round(pn, 4), round(pg, 4),
                               round(pp - pg, 4), round(float(p.max()), 4), r[3]))
            execute_values(cur, """
                INSERT INTO analytics.article_sentiment (article_id, model_version, label, prob_positive,
                       prob_neutral, prob_negative, sentiment_score, confidence, content_hash)
                VALUES %s
                ON CONFLICT (article_id, model_version) DO UPDATE
                SET label = EXCLUDED.label, prob_positive = EXCLUDED.prob_positive,
                    prob_neutral = EXCLUDED.prob_neutral, prob_negative = EXCLUDED.prob_negative,
                    sentiment_score = EXCLUDED.sentiment_score, confidence = EXCLUDED.confidence,
                    content_hash = EXCLUDED.content_hash, predicted_at = now()""", values)
            log.loaded += len(values)
        conn.commit()
        print(f"  [predict] mô hình {version}: chấm điểm {log.loaded} bài")
        return [r[0] for r in rows]


def extract_keywords(conn, article_ids):
    """Từ khóa = từ ghép tiếng Việt có TF-IDF cao nhất trong bài (IDF tính trên toàn bộ kho bài)."""
    if not article_ids:
        return 0
    with RunLog(conn, "ai:extract_keywords") as log, conn.cursor() as cur:
        cur.execute("SELECT article_id, title, summary FROM core.article ORDER BY article_id")
        corpus = cur.fetchall()
        texts = [f"{t} . {s or ''}" for _, t, s in corpus]
        vec = TfidfVectorizer(analyzer=keyword_analyzer, min_df=3, max_df=0.2, sublinear_tf=True)
        matrix = vec.fit_transform(texts)
        vocab = np.array(vec.get_feature_names_out())
        wanted = set(article_ids)
        values = []
        for row_i, (aid, _, _) in enumerate(corpus):
            if aid not in wanted:
                continue
            row = matrix.getrow(row_i)
            if row.nnz == 0:
                continue
            order = np.argsort(-row.data)[:TOP_K_KEYWORDS]
            for rank, j in enumerate(order, start=1):
                values.append((aid, vocab[row.indices[j]], round(float(row.data[j]), 4), rank))
        ids = list(wanted)
        for i in range(0, len(ids), 1000):
            cur.execute("DELETE FROM analytics.article_keyword WHERE article_id = ANY(%s)", (ids[i:i + 1000],))
        execute_values(cur, "INSERT INTO analytics.article_keyword (article_id, keyword, weight, rank) VALUES %s",
                       values, page_size=1000)
        conn.commit()
        log.extracted, log.loaded = len(wanted), len(values)
        print(f"  [keywords] {len(values)} từ khóa cho {len(wanted)} bài (từ điển {len(vocab)} từ ghép)")
        return len(values)


def run(conn):
    ids = predict_sentiment(conn)
    extract_keywords(conn, ids)
