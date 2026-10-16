"""PHẦN 2 (mở rộng) - DỰ BÁO CHỈ SỐ CẢM XÚC 14 NGÀY TỚI theo từng chuyên mục.

Chỉ số cảm xúc = trung bình sentiment_score của các bài trong 7 ngày gần nhất (trượt, thang -1..1).
Dùng trung bình trượt 7 ngày vì mỗi chuyên mục chỉ có vài bài/ngày -> số liệu từng ngày rất nhiễu.

Mô hình chính: AR(1) hồi quy về trung bình - chỉ số cảm xúc dao động quanh mức nền của chuyên mục,
các "cú sốc" (sự kiện) tắt dần theo hệ số phi. So sánh bằng backtest cuộn (rolling-origin) với:
  - mô hình ngây thơ (giữ nguyên giá trị cuối)
  - Holt (làm trơn hàm mũ có xu hướng tắt dần)
"""
from datetime import timedelta

import numpy as np
from psycopg2.extras import execute_values

from ..db import RunLog

HORIZON = 14
HISTORY_DAYS = 150
FIT_WINDOW = 90
MODEL_NAME = "ar1-mean-reverting-v1"


# ----------------------------------------------------------------------------- các mô hình
def ar1_forecast(y, horizon=HORIZON):
    """y_t - mu = phi * (y_{t-1} - mu) + e_t  ->  dự báo hội tụ dần về mu."""
    w = y[-FIT_WINDOW:]
    mu = float(w.mean())
    x = w - mu
    phi = float(np.clip((x[1:] @ x[:-1]) / max(x[:-1] @ x[:-1], 1e-9), 0.0, 0.99))
    resid = x[1:] - phi * x[:-1]
    sigma = float(resid.std()) if len(resid) > 2 else 0.1
    h = np.arange(1, horizon + 1)
    point = mu + (y[-1] - mu) * phi ** h
    # sai số tích lũy của AR(1): sigma * sqrt(sum_{k<h} phi^(2k))
    spread = sigma * np.sqrt(np.cumsum(phi ** (2 * np.arange(horizon))))
    lo, hi = point - 1.96 * spread, point + 1.96 * spread
    return np.clip(point, -1, 1), np.clip(lo, -1, 1), np.clip(hi, -1, 1), {"mu": mu, "phi": phi, "sigma": sigma}


def holt_forecast(y, horizon=HORIZON, phi=0.9):
    best = None
    for a in np.arange(0.05, 0.75, 0.05):
        for b in (0.01, 0.05, 0.1, 0.2):
            level, trend, sse = y[0], 0.0, 0.0
            for t in range(1, len(y)):
                err = y[t] - (level + phi * trend)
                if t > 7:
                    sse += err * err
                new_level = a * y[t] + (1 - a) * (level + phi * trend)
                trend = b * (new_level - level) + (1 - b) * phi * trend
                level = new_level
            if best is None or sse < best[0]:
                best = (sse, level, trend)
    _, level, trend = best
    damp = np.cumsum(phi ** np.arange(1, horizon + 1))
    return np.clip(level + damp * trend, -1, 1)


def backtest(y, n_origins=7, step=7):
    """Backtest cuộn: tại mỗi mốc, chỉ dùng dữ liệu quá khứ dự báo 14 ngày tiếp theo, tính MAE."""
    maes = {"ar1": [], "holt": [], "naive": []}
    last_origin = len(y) - HORIZON
    for o in range(last_origin - (n_origins - 1) * step, last_origin + 1, step):
        if o < 30:
            continue
        train, test = y[:o], y[o:o + HORIZON]
        maes["ar1"].append(np.abs(ar1_forecast(train)[0] - test).mean())
        maes["holt"].append(np.abs(holt_forecast(train) - test).mean())
        maes["naive"].append(np.abs(train[-1] - test).mean())
    return {k: float(np.mean(v)) for k, v in maes.items() if v}


# ----------------------------------------------------------------------------- dữ liệu
def sentiment_index_7d(cur, category_code):
    cond = "" if category_code == "all" else "AND v.category_code = %s"
    params = () if category_code == "all" else (category_code,)
    cur.execute(f"""SELECT v.published_date, SUM(v.sentiment_score)::float, COUNT(*)
                    FROM analytics.v_article_sentiment v
                    WHERE v.published_date > (SELECT MAX(published_date) FROM core.article) - {HISTORY_DAYS}
                    {cond}
                    GROUP BY v.published_date ORDER BY v.published_date""", params)
    rows = cur.fetchall()
    if not rows:
        return None, None
    data = {r[0]: (r[1], r[2]) for r in rows}
    dates, sums, counts = [], [], []
    d = rows[0][0]
    while d <= rows[-1][0]:  # chuỗi ngày liên tục, ngày không có bài: tổng = 0, số bài = 0
        s_, n_ = data.get(d, (0.0, 0))
        dates.append(d)
        sums.append(s_)
        counts.append(n_)
        d += timedelta(days=1)
    kernel = np.ones(7)
    roll_s = np.convolve(np.array(sums), kernel)[:len(sums)]
    roll_n = np.convolve(np.array(counts, dtype=float), kernel)[:len(counts)]
    index_7d = roll_s / np.maximum(roll_n, 1)
    return dates[6:], index_7d[6:]  # bỏ 6 ngày đầu chưa đủ cửa sổ


def run(conn):
    with RunLog(conn, "ai:forecast_sentiment") as log, conn.cursor() as cur:
        cur.execute("SELECT category_code FROM core.dim_category WHERE category_code <> 'khac'")
        cats = ["all"] + [r[0] for r in cur.fetchall()]
        values, summary = [], []
        for cat in cats:
            dates, y = sentiment_index_7d(cur, cat)
            if y is None or len(y) < 60:
                continue
            bt = backtest(y)
            point, lo, hi, params = ar1_forecast(y)
            for h in range(HORIZON):
                values.append((cat, dates[-1] + timedelta(days=h + 1), round(float(point[h]), 4),
                               round(float(lo[h]), 4), round(float(hi[h]), 4), MODEL_NAME, round(bt["ar1"], 4)))
            summary.append(bt)
            print(f"  [forecast] {cat:<10} MAE backtest: AR(1) {bt['ar1']:.4f} | Holt {bt['holt']:.4f} | "
                  f"ngây thơ {bt['naive']:.4f} || mức nền {params['mu']:+.3f}, phi {params['phi']:.2f} | "
                  f"hiện tại {y[-1]:+.3f} -> +14 ngày {point[-1]:+.3f}")
        cur.execute("DELETE FROM analytics.sentiment_forecast")
        execute_values(cur, """INSERT INTO analytics.sentiment_forecast (category_code, forecast_date,
                               predicted_index, lower_bound, upper_bound, model_version, backtest_mae)
                               VALUES %s""", values)
        conn.commit()
        log.loaded = len(values)
        if summary:
            avg = {k: np.mean([s[k] for s in summary]) for k in summary[0]}
            print(f"  [forecast] MAE trung bình: AR(1) {avg['ar1']:.4f} | Holt {avg['holt']:.4f} | "
                  f"ngây thơ {avg['naive']:.4f}")
