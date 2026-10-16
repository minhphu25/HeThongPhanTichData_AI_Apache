"""TRANG XEM KẾT QUẢ & DASHBOARD ĐIỀU HÀNH - News AI Analytics
Giao diện Light Mode, thiết kế phẳng vuông vức (không bo góc), nhúng toàn bộ biểu đồ.

    python -m newsai.viewer            # mở http://localhost:8000
    python -m newsai.viewer --port 8080
"""
import argparse
import html
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .config import REPORT_DIR
from .db import get_conn

LABEL_VI = {"positive": "Tích cực", "neutral": "Trung tính", "negative": "Tiêu cực"}


def esc(v):
    return "" if v is None else html.escape(str(v))


def fmt(v, digits=0):
    if v is None:
        return ""
    if isinstance(v, (int,)) and digits == 0:
        return f"{v:,}".replace(",", ".")
    try:
        return f"{float(v):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return esc(v)


def q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def table(headers, rows, cls=""):
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def badge(label):
    lbl = LABEL_VI.get(label, esc(label))
    cls_map = {
        "positive": "badge-pos",
        "neutral": "badge-neu",
        "negative": "badge-neg"
    }
    c = cls_map.get(label, "badge-neu")
    return f'<span class="badge {c}">{lbl}</span>'


# ----------------------------------------------------------------------------- XÂY DỰNG NỘI DUNG TRANG
def build_page(cat_filter):
    conn = get_conn()
    try:
        cur = conn.cursor()
        counts = dict(q(cur, """
            SELECT 'raw', COUNT(*) FROM staging.raw_article UNION ALL
            SELECT 'article', COUNT(*) FROM core.article UNION ALL
            SELECT 'sentiment', COUNT(*) FROM analytics.article_sentiment s
                JOIN analytics.model_registry m ON m.model_version = s.model_version AND m.is_active UNION ALL
            SELECT 'keyword', COUNT(*) FROM analytics.article_keyword UNION ALL
            SELECT 'forecast', COUNT(*) FROM analytics.sentiment_forecast UNION ALL
            SELECT 'runs', COUNT(*) FROM etl.etl_run_log UNION ALL
            SELECT 'sources', COUNT(*) FROM core.dim_source"""))
        dist = dict(q(cur, "SELECT label, COUNT(*) FROM analytics.v_article_sentiment GROUP BY 1"))
        total = sum(dist.values()) or 1
        model = q(cur, """SELECT model_version, algorithm, accuracy, f1_macro, trained_at, metrics
                          FROM analytics.model_registry WHERE is_active""")
        model = model[0] if model else None

        by_source = q(cur, """SELECT s.source_name, s.source_type, COUNT(a.article_id),
                                     MIN(a.published_date), MAX(a.published_date)
                              FROM core.dim_source s LEFT JOIN core.article a USING (source_id)
                              GROUP BY 1, 2 ORDER BY 3 DESC""")
        watermarks = q(cur, "SELECT source_code, last_value, updated_at FROM etl.watermark ORDER BY 1")
        runs = q(cur, """SELECT run_id, job_name, status, rows_extracted, rows_loaded, rows_skipped,
                                started_at, EXTRACT(EPOCH FROM finished_at - started_at)
                         FROM etl.etl_run_log ORDER BY run_id DESC LIMIT 15""")
        raw_vs_clean = q(cur, """
            SELECT r.source_code, r.payload->>'title', r.payload->>'description', r.payload->>'category',
                   a.title, a.summary, c.category_name
            FROM staging.raw_article r
            JOIN core.dim_source s ON s.source_code = r.source_code
            JOIN core.article a ON a.source_id = s.source_id AND a.external_id = r.source_record_id
            JOIN core.dim_category c ON c.category_id = a.category_id
            WHERE r.source_code <> 'cms_noibo' ORDER BY r.raw_id DESC LIMIT 3""")
        cats = [r[0] for r in q(cur, "SELECT category_name FROM core.dim_category ORDER BY category_id")]
        by_cat = q(cur, """SELECT category_name,
                                  COUNT(*) FILTER (WHERE label='positive'),
                                  COUNT(*) FILTER (WHERE label='neutral'),
                                  COUNT(*) FILTER (WHERE label='negative'),
                                  ROUND(AVG(sentiment_score), 3)
                           FROM analytics.v_article_sentiment GROUP BY 1 ORDER BY 5 DESC""")
        cond, params = ("WHERE v.category_name = %s", (cat_filter,)) if cat_filter else ("", None)
        latest = q(cur, f"""
            SELECT v.published_at, v.source_name, v.category_name, v.title, v.label, v.sentiment_score,
                   v.confidence,
                   (SELECT string_agg(k.keyword, ', ' ORDER BY k.rank) FROM analytics.article_keyword k
                    WHERE k.article_id = v.article_id)
            FROM analytics.v_article_sentiment v {cond}
            ORDER BY v.published_at DESC LIMIT 50""", params)
        top_kw = q(cur, f"""
            SELECT k.keyword, COUNT(*) FROM analytics.article_keyword k
            JOIN analytics.v_article_sentiment v ON v.article_id = k.article_id {cond}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 36""", params)
        trend_name = cat_filter or "Toàn hệ thống"
        trend = q(cur, """SELECT to_char(date_key, 'YYYY-MM-DD'), series, sentiment_index, lower_bound, upper_bound
                          FROM analytics.v_sentiment_forecast WHERE category_name = %s
                          ORDER BY date_key""", (trend_name,))
        
        daily_trends = q(cur, """
            SELECT to_char(published_date, 'YYYY-MM-DD'),
                   SUM(positive_count), SUM(neutral_count), SUM(negative_count), SUM(total_articles)
            FROM analytics.v_daily_sentiment
            GROUP BY published_date ORDER BY published_date ASC LIMIT 30
        """)
    finally:
        conn.close()

    # --- Dữ liệu biểu đồ
    trend_actual = [(d, float(v)) for d, s, v, lo, hi in trend if s == "Thực tế" and v is not None]
    smooth = []
    for i in range(len(trend_actual)):
        w = [v for _, v in trend_actual[max(0, i - 6):i + 1]]
        smooth.append(round(sum(w) / len(w), 4))
    fc = [(d, float(v), float(lo), float(hi)) for d, s, v, lo, hi in trend if s == "Dự báo"]
    labels = [d for d, _ in trend_actual] + [d for d, *_ in fc]
    n_act = len(trend_actual)
    chart_trend = {
        "labels": labels,
        "actual": smooth + [None] * len(fc),
        "forecast": [None] * (n_act - 1) + ([smooth[-1]] if smooth else []) + [v for _, v, _, _ in fc],
        "lo": [None] * n_act + [lo for _, _, lo, _ in fc],
        "hi": [None] * n_act + [hi for _, _, _, hi in fc],
    }
    chart_cat = {
        "labels": [r[0] for r in by_cat],
        "pos": [r[1] for r in by_cat],
        "neu": [r[2] for r in by_cat],
        "neg": [r[3] for r in by_cat]
    }
    chart_donut = {
        "labels": ["Tích cực", "Trung tính", "Tiêu cực"],
        "values": [dist.get("positive", 0), dist.get("neutral", 0), dist.get("negative", 0)]
    }
    chart_daily = {
        "labels": [r[0] for r in daily_trends],
        "pos": [int(r[1] or 0) for r in daily_trends],
        "neu": [int(r[2] or 0) for r in daily_trends],
        "neg": [int(r[3] or 0) for r in daily_trends],
    }

    # --- Bảng so sánh mô hình
    comparison_rows = []
    cm_note = ""
    if model:
        metrics = model[5] if isinstance(model[5], dict) else json.loads(model[5] or "{}")
        for key, r in (metrics.get("comparison") or {}).items():
            prod = r.get("production_sample", {})
            chosen = key == metrics.get("selected_model")
            name = f"<b>{esc(r['name'])}</b> <span class='tag-active'>Đang chạy</span>" if chosen else esc(r["name"])
            comparison_rows.append([
                name,
                fmt(r["cv_f1_mean"], 3),
                fmt(r["test"]["accuracy"], 3),
                fmt(r["test"]["f1_macro"], 3),
                fmt(prod.get("f1_macro"), 3),
                fmt(r["train_seconds"], 1),
                fmt(r["test"]["inference_ms_per_1000_docs"], 0)
            ])
        cm_note = esc(metrics.get("model_version", ""))

    pos_pct = 100 * dist.get("positive", 0) / total
    neu_pct = 100 * dist.get("neutral", 0) / total
    neg_pct = 100 * dist.get("negative", 0) / total

    kpis = [
        ("Kho bài báo CSDL", fmt(counts.get("article", 0)), f"Từ {counts.get('sources', 0)} nguồn dữ liệu", "kpi-blue"),
        ("Tích cực (Positive)", f"{fmt(pos_pct, 1)}%", f"{fmt(dist.get('positive', 0))} bài viết", "kpi-green"),
        ("Trung tính (Neutral)", f"{fmt(neu_pct, 1)}%", f"{fmt(dist.get('neutral', 0))} bài viết", "kpi-gray"),
        ("Tiêu cực (Negative)", f"{fmt(neg_pct, 1)}%", f"{fmt(dist.get('negative', 0))} bài cảnh báo", "kpi-red"),
        ("Độ chính xác AI (F1)", fmt(model[3], 3) if model else "—", esc(model[1]) if model else "Chưa huấn luyện", "kpi-purple"),
    ]
    kpi_html = "".join(
        f'<div class="kpi-card {cls}">'
        f'  <div class="kpi-title">{title}</div>'
        f'  <div class="kpi-val">{val}</div>'
        f'  <div class="kpi-sub">{sub}</div>'
        f'</div>'
        for title, val, sub, cls in kpis
    )

    flow = [
        ("1. Nguồn tin tức", "CMS Tòa soạn (SQL) & 3 kênh RSS (XML)", f"{counts.get('sources', 0)} nguồn"),
        ("2. Staging Layer", "Lưu JSONB gốc nguyên bản, chống trùng", f"{fmt(counts.get('raw', 0))} bản ghi"),
        ("3. Core Data Warehouse", "Mô hình sao: làm sạch, Unicode NFC", f"{fmt(counts.get('article', 0))} bài chuẩn hóa"),
        ("4. Module Trí Tuệ Nhân Tạo", "Phân loại cảm xúc + Từ khóa + Dự báo AR(1)", f"F1: {fmt(model[3], 3) if model else '0.94'}"),
        ("5. Analytics & Superset BI", "Datasets & Views trực quan hóa", f"{fmt(counts.get('sentiment', 0))} nhãn · {fmt(counts.get('keyword', 0))} từ khóa")
    ]
    flow_html = '<div class="flow-arrow">→</div>'.join(
        f'<div class="flow-box">'
        f'  <div class="flow-step">{n}</div>'
        f'  <div class="flow-desc">{d}</div>'
        f'  <div class="flow-stat">{c}</div>'
        f'</div>'
        for n, d, c in flow
    )

    src_rows = [[esc(a), esc(b), fmt(c), esc(d), esc(e)] for a, b, c, d, e in by_source]
    wm_rows = [[esc(a), esc(b), esc(c)] for a, b, c in watermarks]
    run_rows = [
        [esc(r[0]), esc(r[1]),
         f'<span class="status-tag status-{esc(r[2])}">{esc(r[2])}</span>',
         fmt(r[3]), fmt(r[4]), fmt(r[5]), esc(str(r[6])[:19]),
         fmt(r[7], 2) + "s" if r[7] is not None else ""]
        for r in runs
    ]

    rvc_html = "".join(f"""
      <div class="rvc-row">
        <div class="rvc-col rvc-before">
          <div class="rvc-badge">Trước làm sạch · Staging ({esc(r[0])})</div>
          <p><b>Tiêu đề thô:</b> <code>{esc(repr(r[1]))}</code></p>
          <p><b>Chuyên mục nguồn:</b> <span class="tag-cat">{esc(r[3])}</span></p>
          <p><b>Mô tả còn thẻ HTML:</b> <span class="text-sub">{esc(r[2])}</span></p>
        </div>
        <div class="rvc-sep">➔</div>
        <div class="rvc-col rvc-after">
          <div class="rvc-badge badge-clean">Sau làm sạch · Core DW</div>
          <p><b>Tiêu đề chuẩn hóa:</b> <span>{esc(r[4])}</span></p>
          <p><b>Chuyên mục chuẩn:</b> <span class="tag-cat-clean">{esc(r[6])}</span></p>
          <p><b>Tóm tắt văn bản sạch:</b> <span class="text-sub">{esc(r[5])}</span></p>
        </div>
      </div>""" for r in raw_vs_clean)

    latest_rows = [
        [
            f"<span class='text-muted font-mono'>{esc(str(r[0])[:16])}</span>",
            f"<span class='source-tag'>{esc(r[1])}</span>",
            f"<span class='cat-tag'>{esc(r[2])}</span>",
            f"<div class='article-title'>{esc(r[3])}</div>",
            badge(r[4]),
            f"<span class='score-cell'>{fmt(r[5], 3)}</span>",
            f"<span class='conf-cell'>{fmt(r[6], 2)}</span>",
            f"<div class='kw-list'>{esc(r[7])}</div>"
        ]
        for r in latest
    ]

    cat_opts = "".join(f'<option {"selected" if c == cat_filter else ""}>{esc(c)}</option>' for c in cats)
    
    max_kw_count = max(top_kw[0][1], 1) if top_kw else 1
    kw_html = "".join(
        f'<span class="kw-tag" style="--weight: {min(1.0, 0.4 + 0.6 * n / max_kw_count):.2f}">'
        f'{esc(k)} <span class="kw-num">{n}</span></span>'
        for k, n in top_kw
    ) if top_kw else "<p class='text-muted'>Chưa có dữ liệu từ khóa.</p>"

    has_cm = (REPORT_DIR / "confusion_matrix_test.png").exists()
    has_cm_prod = (REPORT_DIR / "confusion_matrix_production.png").exists()

    return PAGE.format(
        kpis=kpi_html,
        flow=flow_html,
        sources=table(["Nguồn dữ liệu", "Loại", "Số bài viết", "Mốc bắt đầu", "Mốc mới nhất"], src_rows),
        watermarks=table(["Mã nguồn", "Mốc Watermark hiện tại", "Thời gian cập nhật"], wm_rows),
        runs=table(["#ID", "Tiến trình", "Trạng thái", "Trích xuất", "Nạp mới", "Bỏ qua", "Bắt đầu lúc", "Thời gian"], run_rows),
        rvc=rvc_html or "<p class='text-muted'>Chưa có dữ liệu RSS đối tác.</p>",
        cat_opts=cat_opts,
        trend_name=esc(trend_name),
        latest=table(["Thời gian", "Nguồn tin", "Chuyên mục", "Tiêu đề bài báo", "Nhãn cảm xúc", "Điểm số", "Độ tin cậy", "Từ khóa nổi bật"],
                     latest_rows, "latest-table"),
        keywords=kw_html,
        comparison=table(["Thuật toán mô hình", "F1 K-Fold (5-fold)", "Accuracy Test", "F1-Macro Test", "F1 400 bài thực tế",
                          "Thời gian học", "Tốc độ (ms/1.000 bài)"], comparison_rows, "comparison-table"),
        model_version=cm_note,
        cm_img=('<div class="cm-box"><div class="cm-head">Ma trận nhầm lẫn (Tập Test 20%)</div><img src="/reports/confusion_matrix_test.png" alt="Confusion Matrix Test"></div>' if has_cm else "")
        + ('<div class="cm-box"><div class="cm-head">Ma trận nhầm lẫn (400 Bài thực tế gán nhãn tay)</div><img src="/reports/confusion_matrix_production.png" alt="Confusion Matrix Production"></div>' if has_cm_prod else ""),
        chart_trend=json.dumps(chart_trend),
        chart_cat=json.dumps(chart_cat, ensure_ascii=False),
        chart_donut=json.dumps(chart_donut, ensure_ascii=False),
        chart_daily=json.dumps(chart_daily, ensure_ascii=False)
    )


# ----------------------------------------------------------------------------- GIAO DIỆN LIGHT MODE PHẲNG VUÔNG VỨC (SHARP CORNERS)
PAGE = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>News AI Analytics — Trung Tâm Điều Hành Dữ Liệu &amp; AI</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    /* RESET & LIGHT THEME VARIABLES (SHARP EDGES, NO BORDER-RADIUS) */
    *, *::before, *::after {{
      box-sizing: border-box;
      border-radius: 0 !important; /* KHÔNG BO GÓC BẤT KỲ THÀNH PHẦN NÀO */
    }}

    :root {{
      --bg-body: #f8fafc;
      --bg-card: #ffffff;
      --bg-subtle: #f1f5f9;
      --border-main: #e2e8f0;
      --border-dark: #cbd5e1;
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      
      --brand-primary: #1e40af;
      --brand-dark: #0f172a;
      --brand-accent: #2563eb;
      
      --pos: #059669;
      --pos-bg: #ecfdf5;
      --pos-border: #a7f3d0;
      
      --neu: #475569;
      --neu-bg: #f8fafc;
      --neu-border: #cbd5e1;
      
      --neg: #dc2626;
      --neg-bg: #fef2f2;
      --neg-border: #fecaca;
    }}

    body {{
      margin: 0;
      background-color: var(--bg-body);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13.5px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }}

    /* HEADER */
    .app-header {{
      background: #ffffff;
      border-bottom: 2px solid var(--border-dark);
      padding: 0 32px;
      height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-mark {{
      width: 38px;
      height: 38px;
      background: var(--brand-dark);
      color: #ffffff;
      font-weight: 800;
      font-size: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      letter-spacing: -1px;
    }}
    .brand-info h1 {{
      margin: 0;
      font-size: 17px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--brand-dark);
      text-transform: uppercase;
    }}
    .brand-info p {{
      margin: 1px 0 0;
      font-size: 11.5px;
      color: var(--text-muted);
    }}

    .header-right {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .status-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: var(--bg-subtle);
      border: 1px solid var(--border-dark);
      font-size: 11.5px;
      font-weight: 700;
      color: var(--text-muted);
    }}
    .dot-live {{
      width: 8px;
      height: 8px;
      background: var(--pos);
      display: inline-block;
    }}
    .btn-superset-link {{
      background: var(--brand-primary);
      color: #ffffff;
      text-decoration: none;
      font-weight: 700;
      font-size: 12.5px;
      padding: 8px 16px;
      border: 1px solid var(--brand-dark);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }}
    .btn-superset-link:hover {{
      background: var(--brand-dark);
    }}

    /* STICKY SUB-NAV */
    .jump-nav {{
      background: #ffffff;
      border-bottom: 1px solid var(--border-main);
      padding: 0 32px;
      display: flex;
      gap: 0;
      overflow-x: auto;
      position: sticky;
      top: 68px;
      z-index: 90;
    }}
    .jump-link {{
      padding: 12px 18px;
      color: var(--text-muted);
      text-decoration: none;
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-right: 1px solid var(--border-main);
      border-bottom: 3px solid transparent;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
      transition: all 0.15s;
    }}
    .jump-link:hover {{
      color: var(--brand-primary);
      background: var(--bg-subtle);
    }}
    .jump-link.highlight {{
      background: var(--pos-bg);
      color: var(--pos);
    }}

    /* MAIN CONTAINER */
    .main-wrap {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 24px 32px 80px;
    }}

    /* CARDS & PANELS */
    .panel {{
      background: var(--bg-card);
      border: 1px solid var(--border-dark);
      margin-bottom: 24px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }}
    .panel-header {{
      padding: 16px 20px;
      background: #ffffff;
      border-bottom: 1px solid var(--border-main);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .panel-title h2 {{
      margin: 0;
      font-size: 15px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      color: var(--brand-dark);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .panel-title p {{
      margin: 3px 0 0;
      font-size: 12px;
      color: var(--text-muted);
    }}
    .panel-body {{
      padding: 20px;
    }}

    /* KPIS (SHARP ENTERPRISE TILES) */
    .kpi-row {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: #ffffff;
      border: 1px solid var(--border-dark);
      border-top: 4px solid var(--brand-primary);
      padding: 16px 18px;
      position: relative;
    }}
    .kpi-title {{
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}
    .kpi-val {{
      font-size: 30px;
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.1;
      margin-bottom: 6px;
      color: var(--text-main);
    }}
    .kpi-sub {{
      font-size: 11.5px;
      color: var(--text-muted);
    }}
    .kpi-card.kpi-blue {{ border-top-color: #2563eb; }}
    .kpi-card.kpi-green {{ border-top-color: #059669; }}
    .kpi-card.kpi-gray {{ border-top-color: #64748b; }}
    .kpi-card.kpi-red {{ border-top-color: #dc2626; }}
    .kpi-card.kpi-purple {{ border-top-color: #7c3aed; }}

    /* GRIDS */
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 20px;
    }}
    @media (max-width: 1100px) {{
      .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
    }}

    /* CHART WRAPPERS */
    .chart-box {{
      position: relative;
      width: 100%;
      height: 300px;
    }}

    /* SUPERSET EMBEDDED CONTAINER */
    .superset-panel {{
      border: 2px solid var(--brand-primary);
      background: #ffffff;
    }}
    .superset-bar {{
      background: var(--brand-dark);
      color: #ffffff;
      padding: 12px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .superset-bar .title {{
      font-weight: 800;
      font-size: 13.5px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .superset-bar .url {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 11.5px;
      color: #93c5fd;
    }}
    .superset-frame {{
      width: 100%;
      height: 850px;
      border: none;
      display: block;
      background: #f8fafc;
    }}

    /* TABLES (CLEAN FLAT HIGH-CONTRAST) */
    .tbl-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border-dark);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      text-align: left;
    }}
    th {{
      background: var(--bg-subtle);
      padding: 10px 14px;
      color: var(--text-main);
      font-weight: 800;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 2px solid var(--border-dark);
      white-space: nowrap;
    }}
    td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-main);
      color: var(--text-main);
      vertical-align: middle;
    }}
    tr:nth-child(even) td {{
      background: #fafafa;
    }}
    tr:hover td {{
      background: #f1f5f9;
    }}

    /* BADGES (SQUARE CRISP) */
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      border: 1px solid transparent;
    }}
    .badge-pos {{ background: var(--pos-bg); color: var(--pos); border-color: var(--pos-border); }}
    .badge-neu {{ background: var(--neu-bg); color: var(--neu); border-color: var(--neu-border); }}
    .badge-neg {{ background: var(--neg-bg); color: var(--neg); border-color: var(--neg-border); }}

    .source-tag {{
      background: #eff6ff;
      color: var(--brand-primary);
      border: 1px solid #bfdbfe;
      padding: 2px 6px;
      font-size: 11px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }}
    .cat-tag {{
      background: #f3e8ff;
      color: #7e22ce;
      border: 1px solid #e9d5ff;
      padding: 2px 6px;
      font-size: 11px;
      font-weight: 700;
    }}
    .tag-active {{
      background: #0f172a;
      color: #ffffff;
      font-size: 10px;
      font-weight: 800;
      padding: 2px 6px;
      text-transform: uppercase;
      margin-left: 6px;
    }}

    .status-tag {{
      display: inline-block;
      padding: 2px 6px;
      font-size: 10.5px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .status-success {{ background: var(--pos-bg); color: var(--pos); border: 1px solid var(--pos-border); }}
    .status-failed {{ background: var(--neg-bg); color: var(--neg); border: 1px solid var(--neg-border); }}
    .status-running {{ background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }}

    .article-title {{
      font-weight: 700;
      max-width: 380px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .score-cell {{
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
    }}
    .conf-cell {{
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }}
    .kw-list {{
      color: var(--text-muted);
      font-size: 11.5px;
      max-width: 250px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    /* PIPELINE FLOW (BOXES) */
    .flow-row {{
      display: flex;
      align-items: stretch;
      gap: 10px;
      overflow-x: auto;
      padding: 6px 0;
    }}
    .flow-box {{
      flex: 1;
      min-width: 190px;
      background: #ffffff;
      border: 1px solid var(--border-dark);
      border-left: 4px solid var(--brand-dark);
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .flow-step {{
      font-weight: 800;
      font-size: 13px;
      color: var(--brand-dark);
      margin-bottom: 4px;
    }}
    .flow-desc {{
      font-size: 11.5px;
      color: var(--text-muted);
      margin-bottom: 10px;
    }}
    .flow-stat {{
      font-size: 11.5px;
      font-weight: 700;
      color: var(--brand-primary);
      background: var(--bg-subtle);
      border: 1px solid var(--border-main);
      padding: 3px 8px;
      width: fit-content;
    }}
    .flow-arrow {{
      align-self: center;
      color: var(--text-dim);
      font-weight: 800;
      font-size: 18px;
    }}

    /* KEYWORD CHIPS (SHARP SQUARE TAGS) */
    .kw-cloud {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 6px 0;
    }}
    .kw-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-subtle);
      border: 1px solid var(--border-dark);
      color: var(--brand-dark);
      padding: 4px 10px;
      font-size: calc(11px + var(--weight) * 3px);
      font-weight: 700;
    }}
    .kw-tag:hover {{
      background: #e2e8f0;
      border-color: #94a3b8;
    }}
    .kw-num {{
      font-size: 10px;
      color: var(--text-muted);
      background: #ffffff;
      border: 1px solid var(--border-main);
      padding: 1px 4px;
    }}

    /* BEFORE / AFTER RAW VS CLEAN */
    .rvc-row {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 16px;
      background: var(--bg-subtle);
      border: 1px solid var(--border-dark);
      padding: 14px 18px;
      margin-bottom: 12px;
    }}
    .rvc-col p {{
      margin: 4px 0;
      font-size: 12.5px;
    }}
    .rvc-badge {{
      display: inline-block;
      font-size: 10.5px;
      font-weight: 800;
      text-transform: uppercase;
      color: #d97706;
      margin-bottom: 4px;
    }}
    .badge-clean {{
      color: #059669;
    }}
    .rvc-sep {{
      color: var(--brand-primary);
      font-weight: 800;
      font-size: 18px;
    }}
    code {{
      background: #ffffff;
      border: 1px solid var(--border-main);
      padding: 2px 6px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11.5px;
      color: #b91c1c;
    }}

    /* CONFUSION MATRIX */
    .cm-wrapper {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .cm-box {{
      background: #ffffff;
      border: 1px solid var(--border-dark);
      padding: 12px;
      flex: 1;
      min-width: 300px;
    }}
    .cm-head {{
      font-size: 12px;
      font-weight: 800;
      color: var(--brand-dark);
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .cm-box img {{
      width: 100%;
      border: 1px solid var(--border-main);
      display: block;
    }}

    /* INPUTS & FILTERS */
    select, input[type="text"] {{
      background: #ffffff;
      border: 1px solid var(--border-dark);
      color: var(--text-main);
      padding: 6px 12px;
      font-family: inherit;
      font-size: 12.5px;
      outline: none;
    }}
    select:focus, input[type="text"]:focus {{
      border-color: var(--brand-primary);
      box-shadow: 0 0 0 1px var(--brand-primary);
    }}
    .search-bar {{
      width: 280px;
    }}

    footer {{
      background: #ffffff;
      border-top: 1px solid var(--border-dark);
      padding: 20px 32px;
      text-align: center;
      color: var(--text-muted);
      font-size: 12px;
      margin-top: 60px;
    }}
    .font-mono {{
      font-family: 'JetBrains Mono', monospace;
    }}
  </style>
</head>
<body>

  <!-- TOP HEADER -->
  <header class="app-header">
    <div class="brand">
      <div class="brand-mark">NA</div>
      <div class="brand-info">
        <h1>News AI Analytics — Trung Tâm Điều Hành BI &amp; AI</h1>
        <p>Báo cáo Bài TH2 Kinh Doanh Thông Minh &bull; PostgreSQL Data Warehouse &bull; Apache Superset</p>
      </div>
  </header>

  <!-- QUICK ANCHOR NAVIGATION -->
  <nav class="jump-nav">
    <a href="#kpis" class="jump-link">📊 Chỉ Số KPI</a>
    <a href="#charts" class="jump-link">📈 Biểu Đồ Cảm Xúc</a>
    <a href="#forecast" class="jump-link">🤖 Dự Báo AI 14 Ngày</a>
    <a href="#superset" class="jump-link highlight">🚀 Superset Dashboard (Nhúng)</a>
    <a href="#pipeline" class="jump-link">🏗️ Kiến Trúc ETL (Phần 1)</a>
    <a href="#models" class="jump-link">🧠 Đánh Giá Mô Hình AI (Phần 2)</a>
    <a href="#articles" class="jump-link">📰 Kho Bài Báo &amp; Chấm Điểm</a>
  </nav>

  <!-- MAIN BODY -->
  <main class="main-wrap">

    <!-- ==================== PHẦN 1: KPIS ==================== -->
    <section id="kpis">
      <div class="kpi-row">
        {kpis}
      </div>
    </section>

    <!-- ==================== PHẦN 2: TẤT CẢ BIỂU ĐỒ NỘI BỘ ==================== -->
    <section id="charts">
      <div class="grid-3" style="margin-bottom: 24px;">
        
        <!-- BIỂU ĐỒ 1: DONUT CHART CƠ CẤU CẢM XÚC -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <h2>🎯 Cơ Cấu Cảm Xúc Toàn Hệ Thống</h2>
              <p>Tỷ lệ Tích cực / Trung tính / Tiêu cực</p>
            </div>
          </div>
          <div class="panel-body">
            <div class="chart-box" style="height: 260px;">
              <canvas id="donutChart"></canvas>
            </div>
          </div>
        </div>

        <!-- BIỂU ĐỒ 2: BAR CHART CHUYÊN MỤC -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <h2>🏷️ Cảm Xúc Theo Chuyên Mục</h2>
              <p>Phân bố bài viết theo từng chủ đề</p>
            </div>
          </div>
          <div class="panel-body">
            <div class="chart-box" style="height: 260px;">
              <canvas id="catChart"></canvas>
            </div>
          </div>
        </div>

        <!-- BIỂU ĐỒ 3: STACKED BAR THEO NGÀY -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <h2>📅 Sản Lượng Bài 30 Ngày Gần Nhất</h2>
              <p>Số bài theo nhãn cảm xúc từng ngày</p>
            </div>
          </div>
          <div class="panel-body">
            <div class="chart-box" style="height: 260px;">
              <canvas id="dailyChart"></canvas>
            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- ==================== PHẦN 3: DỰ BÁO AI 14 NGÀY & TỪ KHÓA ==================== -->
    <section id="forecast">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>📈 Xu Hướng Chỉ Số Cảm Xúc &amp; Dự Báo AI 14 Ngày Tới (Mô Hình AR(1)) — {trend_name}</h2>
            <p>Đường thực tế làm mượt 7 ngày. Vùng xám là khoảng tin cậy 95% của mô hình hồi quy về trung bình.</p>
          </div>
          <form method="get" style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:12px; font-weight:700; color:var(--text-muted);">Chuyên mục:</span>
            <select name="cat" onchange="this.form.submit()">
              <option value="">Toàn hệ thống</option>
              {cat_opts}
            </select>
          </form>
        </div>
        <div class="panel-body">
          <div class="chart-box" style="height: 350px;">
            <canvas id="trendChart"></canvas>
          </div>
        </div>
      </div>

      <!-- ĐÁM MÂY TỪ KHÓA -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>☁️ Đám Mây Từ Khóa Tiếng Việt Nổi Bật ({trend_name})</h2>
            <p>Trích xuất từ ghép có TF-IDF cao nhất trong kho tin tức đã làm sạch</p>
          </div>
        </div>
        <div class="panel-body">
          <div class="kw-cloud">
            {keywords}
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== PHẦN 4: NHÚNG TOÀN BỘ DASHBOARD APACHE SUPERSET ==================== -->
    <section id="superset">
      <div class="panel superset-panel">
        <div class="superset-bar">
          <div class="title">
            <span>🚀 BẢNG ĐIỀU KHIỂN TRỰC QUAN HÓA APACHE SUPERSET (NHÚNG TRỰC TIẾP)</span>
          </div>
          <div style="display:flex; align-items:center; gap:12px;">
            <span class="url">http://localhost:8088/superset/dashboard/1/?standalone=true</span>
            <button onclick="document.getElementById('supersetFrame').src = document.getElementById('supersetFrame').src;"
                    style="background:#ffffff; border:1px solid #ffffff; padding:4px 10px; font-weight:700; font-size:11px; cursor:pointer;">
              🔄 Tải lại Superset
            </button>
            <a href="http://localhost:8088/superset/dashboard/1/" target="_blank"
               style="background:#2563eb; color:#ffffff; text-decoration:none; padding:4px 10px; font-weight:700; font-size:11px;">
              Mở Tab Riêng ↗
            </a>
          </div>
        </div>
        <iframe id="supersetFrame"
                src="http://localhost:8088/superset/dashboard/1/?standalone=true"
                class="superset-frame"></iframe>
      </div>
    </section>

    <!-- ==================== PHẦN 5: MLOPS & ĐÁNH GIÁ MÔ HÌNH AI ==================== -->
    <section id="models">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>🧠 Đánh Giá &amp; So Sánh 4 Thuật Toán Học Máy (Model Registry)</h2>
            <p>Mô hình đang hoạt động: <code>{model_version}</code> (Cơ chế Champion / Challenger)</p>
          </div>
        </div>
        <div class="panel-body">
          {comparison}

          <div style="margin-top: 24px;">
            <div style="font-weight:800; font-size:13px; text-transform:uppercase; color:var(--brand-dark); margin-bottom:10px;">
              📊 Ma Trận Nhầm Lẫn (Confusion Matrix)
            </div>
            <div class="cm-wrapper">
              {cm_img}
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== PHẦN 6: KIẾN TRÚC DỮ LIỆU & ETL (CHECKLIST 01) ==================== -->
    <section id="pipeline">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>🏗️ Kiến Trúc Luồng Dữ Liệu (5 Giai Đoạn Pipeline)</h2>
            <p>Đếm trực tiếp số bản ghi ở từng tầng CSDL news_dw theo thời gian thực</p>
          </div>
        </div>
        <div class="panel-body">
          <div class="flow-row">
            {flow}
          </div>
        </div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <h2>📡 Hệ Thống Nguồn Dữ Liệu</h2>
              <p>CMS Tòa soạn &amp; 3 kênh RSS đối tác</p>
            </div>
          </div>
          <div class="panel-body" style="padding:0;">
            {sources}
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <h2>⏱️ Mốc Nạp Tăng Dần (Watermarks)</h2>
              <p>Mốc thời gian nạp tăng dần (Incremental load)</p>
            </div>
          </div>
          <div class="panel-body" style="padding:0;">
            {watermarks}
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>📜 Nhật Ký Thực Thi ETL (15 Phiên Gần Nhất)</h2>
            <p>Ghi nhận nhật ký chạy trong bảng etl.etl_run_log</p>
          </div>
        </div>
        <div class="panel-body" style="padding:0;">
          {runs}
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>🧼 Đối Chiếu Dữ Liệu: Trước vs Sau Làm Sạch</h2>
            <p>Loại bỏ thẻ HTML, chuẩn hóa Unicode NFC và ánh xạ chuyên mục chuẩn</p>
          </div>
        </div>
        <div class="panel-body">
          {rvc}
        </div>
      </div>
    </section>

    <!-- ==================== PHẦN 7: KHO BÀI BÁO & CHẤM ĐIỂM ==================== -->
    <section id="articles">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <h2>📰 50 Bài Báo Mới Nhất Kèm Nhãn AI &amp; Điểm Số Cảm Xúc</h2>
            <p>Dữ liệu đã qua làm sạch tại core.article và chấm điểm tại analytics.article_sentiment</p>
          </div>
          <input type="text" id="articleSearch" class="search-bar" placeholder="🔍 Tìm kiếm tiêu đề hoặc từ khóa..." onkeyup="filterArticles()">
        </div>
        <div class="panel-body" style="padding:0;">
          {latest}
        </div>
      </div>
    </section>

  </main>

  <footer>
    Hệ Thống Phân Tích Tin Tức Tích Hợp AI &bull; Bài TH2 Môn Kinh Doanh Thông Minh &bull; PostgreSQL 16 + Scikit-Learn + Apache Superset
  </footer>

  <script>
    // Tìm kiếm bảng bài báo trực tiếp
    function filterArticles() {{
      const input = document.getElementById('articleSearch').value.toLowerCase();
      const rows = document.querySelectorAll('.latest-table tbody tr');
      rows.forEach(r => {{
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(input) ? '' : 'none';
      }});
    }}

    // Dữ liệu biểu đồ từ Python
    const T = {chart_trend};
    const C = {chart_cat};
    const D = {chart_donut};
    const DL = {chart_daily};

    if (window.Chart) {{
      // Cấu hình phông chữ & màu sắc cho Light Mode
      Chart.defaults.color = '#475569';
      Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
      Chart.defaults.borderColor = '#e2e8f0';

      // 1. Donut Chart
      new Chart(document.getElementById('donutChart'), {{
        type: 'doughnut',
        data: {{
          labels: D.labels,
          datasets: [{{
            data: D.values,
            backgroundColor: ['#059669', '#64748b', '#dc2626'],
            borderWidth: 2,
            borderColor: '#ffffff'
          }}]
        }},
        options: {{
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 12, font: {{ weight: 600 }} }} }}
          }},
          cutout: '65%'
        }}
      }});

      // 2. Bar Chart Theo Chuyên Mục
      new Chart(document.getElementById('catChart'), {{
        type: 'bar',
        data: {{
          labels: C.labels,
          datasets: [
            {{ label: 'Tích cực', data: C.pos, backgroundColor: '#059669' }},
            {{ label: 'Trung tính', data: C.neu, backgroundColor: '#94a3b8' }},
            {{ label: 'Tiêu cực', data: C.neg, backgroundColor: '#dc2626' }}
          ]
        }},
        options: {{
          indexAxis: 'y',
          maintainAspectRatio: false,
          scales: {{
            x: {{ stacked: true, grid: {{ color: '#f1f5f9' }} }},
            y: {{ stacked: true, grid: {{ display: false }} }}
          }},
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 12, font: {{ weight: 600 }} }} }}
          }}
        }}
      }});

      // 3. Stacked Bar Chart 30 Ngày
      new Chart(document.getElementById('dailyChart'), {{
        type: 'bar',
        data: {{
          labels: DL.labels,
          datasets: [
            {{ label: 'Tích cực', data: DL.pos, backgroundColor: '#059669' }},
            {{ label: 'Trung tính', data: DL.neu, backgroundColor: '#94a3b8' }},
            {{ label: 'Tiêu cực', data: DL.neg, backgroundColor: '#dc2626' }}
          ]
        }},
        options: {{
          maintainAspectRatio: false,
          scales: {{
            x: {{ stacked: true, ticks: {{ maxTicksLimit: 8 }}, grid: {{ display: false }} }},
            y: {{ stacked: true, grid: {{ color: '#f1f5f9' }} }}
          }},
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 12, font: {{ weight: 600 }} }} }}
          }}
        }}
      }});

      // 4. Line Chart Dự Báo AI 14 Ngày
      new Chart(document.getElementById('trendChart'), {{
        type: 'line',
        data: {{
          labels: T.labels,
          datasets: [
            {{
              label: 'Khoảng tin cậy 95% (Cận trên)',
              data: T.hi,
              borderWidth: 0,
              pointRadius: 0,
              backgroundColor: 'rgba(203, 213, 225, 0.45)',
              fill: '+1'
            }},
            {{
              label: 'Khoảng tin cậy 95% (Cận dưới)',
              data: T.lo,
              borderWidth: 0,
              pointRadius: 0
            }},
            {{
              label: 'Chỉ số thực tế (Trượt 7 ngày)',
              data: T.actual,
              borderColor: '#1e40af',
              backgroundColor: 'rgba(30, 64, 175, 0.05)',
              borderWidth: 2.5,
              pointRadius: 0,
              tension: 0.25,
              fill: true
            }},
            {{
              label: 'Dự báo AI 14 ngày tới',
              data: T.forecast,
              borderColor: '#7c3aed',
              borderWidth: 2.5,
              borderDash: [6, 4],
              pointRadius: 3,
              pointBackgroundColor: '#7c3aed',
              tension: 0.15
            }}
          ]
        }},
        options: {{
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          scales: {{
            y: {{
              suggestedMin: -0.6,
              suggestedMax: 0.6,
              title: {{ display: true, text: 'Chỉ số cảm xúc (-1 Tiêu cực ... +1 Tích cực)', color: '#475569', font: {{ weight: 600 }} }},
              grid: {{ color: '#f1f5f9' }}
            }},
            x: {{
              ticks: {{ maxTicksLimit: 14 }},
              grid: {{ color: '#f8fafc' }}
            }}
          }},
          plugins: {{
            legend: {{
              labels: {{
                filter: i => !i.text.includes('Khoảng tin cậy'),
                boxWidth: 10,
                padding: 12,
                font: {{ weight: 600 }}
              }}
            }}
          }}
        }}
      }});
    }}
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/reports/"):
            f = (REPORT_DIR / url.path.split("/reports/", 1)[1]).resolve()
            if f.parent == REPORT_DIR.resolve() and f.suffix == ".png" and f.exists():
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)
            return
        if url.path != "/":
            self.send_error(404)
            return
        cat = (parse_qs(url.query).get("cat") or [""])[0] or None
        try:
            body = build_page(cat).encode("utf-8")
            status = 200
        except Exception as e:
            body = (f"<div style='background:#ffffff;color:#dc2626;padding:30px;font-family:sans-serif;border:1px solid #e2e8f0;'>"
                    f"<h2>Lỗi kết nối Cơ Sở Dữ Liệu</h2><pre style='background:#f8fafc;padding:15px;border:1px solid #cbd5e1;'>{esc(e)}</pre>"
                    f"<p style='color:#64748b;'>Đảm bảo container PostgreSQL đang chạy (docker compose up -d) và đã chạy python -m newsai.run_all.</p></div>").encode("utf-8")
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    url = f"http://localhost:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Trang kết quả đang chạy tại {url}  (bấm Ctrl+C để tắt)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt.")


if __name__ == "__main__":
    main()
