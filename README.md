# Hệ thống Phân tích Tin tức tích hợp AI — Phần 1 & 2

Bài TH2 — *Xây dựng Hệ thống Phân tích Dữ liệu Thông minh tích hợp AI và Apache Superset*.
Thư mục này chứa phần việc **Checklist 01** (kiến trúc kết nối dữ liệu Hệ thống Tin tức → CSDL trung tâm)
và **Checklist 02** (triển khai mô hình AI phân tích cảm xúc tin tức).

```
Nguồn tin tức                      ETL (Python)                     CSDL trung tâm PostgreSQL           Superset
──────────────                     ────────────                     ─────────────────────────           ────────
CMS tòa soạn (SQL)  ──┐                                              etl       (watermark, nhật ký)
RSS Tin Nhanh 24h   ──┼─► Connector ─► staging (JSONB gốc) ─► core (bài báo chuẩn hóa) ─► analytics ─► Dashboard
RSS Thời Báo Số     ──┤    (extract)    (load)                 (transform)          ▲    (kết quả AI)  (Phần 3-4)
RSS Nhịp Sống Việt  ──┘                                                             │
                                                    Mô hình AI: cảm xúc + từ khóa + dự báo
```

> Toàn bộ dữ liệu tin tức là **giả lập** (sinh bằng `newsai/sample_data/generate.py`), không phải tin thật.
> Muốn lấy RSS thật: điền URL vào file `.env` (xem `.env.example`).

## 1. Cài đặt và chạy (Windows)

Yêu cầu: Python 3.10+, Docker Desktop (hoặc PostgreSQL 14+ cài sẵn).

```powershell
# 1. Khởi tạo môi trường & cài đặt thư viện
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Khởi động PostgreSQL 16 (port 5433) & Superset 3.0 (port 8088)
docker compose up -d

# 3. Chạy toàn bộ Pipeline: Tạo CSDL -> ETL -> Train AI -> Chấm điểm -> Dự báo
python -m newsai.run_all

# 4. Khởi động Web Dashboard
python -m newsai.viewer
```

Truy cập:
- 🌐 Web Dashboard: [http://localhost:8000](http://localhost:8000)
- 📊 Apache Superset BI: [http://localhost:8088](http://localhost:8088) (`admin` / `admin`)

> 📖 **Xem hướng dẫn chi tiết toàn tập:** Đọc file [HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md) để xem chi tiết cách thiết lập, vận hành, kịch bản demo thuyết trình và giải quyết lỗi.

### Các lệnh vận hành thường dùng (Đi kèm nhau)

```powershell
# Nạp tin mới tăng dần & cập nhật dự báo:
python -m newsai.sample_data.simulate_new_data -n 5
python -m newsai.run_all --steps etl predict forecast

# Huấn luyện lại mô hình AI:
python -m newsai.run_all --steps train

# Dừng hệ thống Docker:
docker compose down
```

## 2. Cấu trúc thư mục

```
sql/01_schema.sql              Schema etl / staging / core / analytics, dữ liệu danh mục, bảng ngày
sql/02_views_superset.sql      Các view cho Superset
sql/03_superset_readonly_user.sql  Tài khoản chỉ đọc superset_reader
newsai/etl/connectors.py       Connector CMS (SQL) và RSS (file/URL)
newsai/etl/pipeline.py         Extract -> staging, Transform -> core, watermark, khử trùng lặp, nhật ký
newsai/ai/text.py              Tiền xử lý tiếng Việt, mô hình từ điển (baseline)
newsai/ai/vi_words.py          Tách từ tiếng Việt (underthesea nếu có, nếu không dùng từ điển)
newsai/ai/train.py             So sánh 4 mô hình, chọn mô hình, đánh giá, đăng ký model_registry
newsai/ai/predict.py           Chấm điểm cảm xúc + trích xuất từ khóa -> analytics
newsai/ai/forecast.py          Dự báo chỉ số cảm xúc 14 ngày (AR(1)), backtest
newsai/sample_data/            Sinh dữ liệu giả lập các hệ thống nguồn
reports/                       Kết quả đánh giá mô hình (JSON, CSV, ma trận nhầm lẫn)
models/                        File mô hình .joblib
```

## 3. Bàn giao cho Phần 3 & 4 (Superset)

**Kết nối Superset → PostgreSQL** (Settings → Database Connections → PostgreSQL):

```
postgresql://superset_reader:superset_reader_123@<host>:5432/news_dw
```
`<host>` = `localhost` nếu Superset chạy trực tiếp trên máy; `host.docker.internal` nếu Superset chạy trong Docker
(hoặc `news_dw_postgres` nếu cùng network `newsnet`).

**Dataset nên tạo** (schema `analytics`):

| View | Nội dung | Biểu đồ gợi ý |
|---|---|---|
| `v_article_sentiment` | Từng bài: nguồn, chuyên mục, thời gian, nhãn (`label_vi`), điểm cảm xúc, độ tin cậy | KPI tổng bài/% tiêu cực, pie theo nhãn, bảng tin tiêu cực mới nhất, heatmap giờ × thứ |
| `v_daily_sentiment` | Theo ngày × chuyên mục × nguồn: số bài từng nhãn, điểm TB, tỷ lệ tiêu cực | Stacked bar theo ngày, so sánh nguồn |
| `v_sentiment_index_7d` | Chỉ số cảm xúc theo ngày và trung bình trượt 7 ngày | Line chart theo chuyên mục |
| `v_sentiment_forecast` | Thực tế + dự báo 14 ngày (`series` = Thực tế / Dự báo), khoảng tin cậy | Line chart dự báo |
| `v_keyword_trend` | Từ khóa theo bài, chuyên mục, nhãn | Word cloud |
| `v_model_performance`, `v_etl_monitoring` | Chất lượng mô hình, nhật ký ETL | Bảng giám sát |

Thang điểm: `sentiment_score` = P(tích cực) − P(tiêu cực), từ −1 (rất tiêu cực) đến +1 (rất tích cực).
