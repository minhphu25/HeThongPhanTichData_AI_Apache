# TÀI LIỆU HƯỚNG DẪN CÀI ĐẶT, VẬN HÀNH VÀ SỬ DỤNG HỆ THỐNG
## Bài TH2 — Hệ Thống Phân Tích Tin Tức Tích Hợp AI & Apache Superset BI
**Môn học:** Kinh Doanh Thông Minh (Business Intelligence)

---

## MỤC LỤC
1. [Hướng Dẫn Setup & Chạy Hệ Thống (Các Câu Lệnh Chính)](#1-hướng-dẫn-setup--chạy-hệ-thống-các-câu-lệnh-chính)
2. [Hướng Dẫn Sử Dụng Trang Web Điều Hành (http://localhost:8000)](#2-hướng-dẫn-sử-dụng-trang-web-điều-hành-httplocalhost8000)
3. [Hướng Dẫn Vận Hành Apache Superset BI (http://localhost:8088)](#3-hướng-dẫn-vận-hành-apache-superset-bi-httplocalhost8088)
4. [Tổng Quan Kiến Trúc Hệ Thống & Dữ Liệu](#4-tổng-quan-kiến-trúc-hệ-thống--dữ-liệu)
5. [Xử Lý Sự Cố Thường Gặp (Troubleshooting)](#5-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. HƯỚNG DẪN SETUP & CHẠY HỆ THỐNG (CÁC CÂU LỆNH CHÍNH)

### 1.1. Yêu cầu chuẩn bị
- **Python 3.10+** (kiểm tra: `python --version`)
- **Docker Desktop** (đảm bảo Docker Desktop đang mở và chạy trước khi gõ lệnh)

---

### 1.2. Khởi chạy toàn bộ hệ thống (4 bước lệnh tuần tự)

Mở PowerShell tại thư mục `news-ai-analytics` và chạy lần lượt các khối lệnh sau:

```powershell
# Bước 1: Khởi tạo môi trường ảo Python & cài đặt thư viện
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Bước 2: Bật CSDL PostgreSQL (port 5433) & Apache Superset (port 8088)
docker compose up -d

# Bước 3: Chạy toàn bộ Pipeline dữ liệu & AI (Init DB -> ETL -> Train AI -> Chấm điểm -> Dự báo)
python -m newsai.run_all

# Bước 4: Khởi động Web Dashboard trực quan hóa
python -m newsai.viewer
```

Sau khi chạy xong, truy cập các địa chỉ:
- 🌐 **Web Dashboard điều hành**: [http://localhost:8000](http://localhost:8000) (đầy đủ KPI, biểu đồ AI & nhúng Superset)
- 📊 **Apache Superset BI**: [http://localhost:8088](http://localhost:8088) (Đăng nhập: `admin` / `admin` — dashboard đã tự động nạp sẵn)
- 🗄️ **PostgreSQL CSDL**: `localhost:5433` (DB: `news_dw` | User: `superset_reader` / `superset_reader_123`)

---

### 1.3. Các cụm lệnh vận hành thường dùng (Luôn đi kèm nhau)

```powershell
# --- Cụm 1: Demo nạp tin mới tăng dần & cập nhật dự báo ---
python -m newsai.sample_data.simulate_new_data -n 5
python -m newsai.run_all --steps etl predict forecast

# --- Cụm 2: Huấn luyện lại mô hình AI (So sánh 4 thuật toán & chọn Champion) ---
python -m newsai.run_all --steps train

# --- Cụm 3: Khởi động lại Web Dashboard (khi mở terminal mới) ---
.venv\Scripts\activate
python -m newsai.viewer

# --- Cụm 4: Dừng toàn bộ hệ thống Docker ---
docker compose down
```

---

## 2. HƯỚNG DẪN SỬ DỤNG TRANG WEB ĐIỀU HÀNH (http://localhost:8000)

Giao diện được thiết kế theo phong cách **Light Mode hiện đại, các khối thẻ phẳng vuông vức (không bo góc), nhúng toàn bộ biểu đồ liền mạch**:

### 2.1. Thanh điều hướng nhanh (Jump Nav)
Nằm cố định ở đầu trang, cho phép nhấp chuột để cuộn nhanh đến các mục:
- **📊 Chỉ Số KPI**: 5 thẻ đo lường hiệu năng tổng quan.
- **📈 Biểu Đồ Cảm Xúc**: Cụm 3 biểu đồ cơ cấu, chuyên mục và sản lượng theo ngày.
- **🤖 Dự Báo AI 14 Ngày**: Biểu đồ chuỗi thời gian dự báo tương lai và đám mây từ khóa.
- **🚀 Superset Dashboard (Nhúng)**: Khung nhúng trực tiếp bảng điều khiển Apache Superset.
- **🏗️ Kiến Trúc ETL (Phần 1)**: Luồng dữ liệu 4 tầng và bảng đối chiếu dữ liệu thô vs sạch.
- **🧠 Đánh Giá Mô Hình AI (Phần 2)**: Bảng MLOps so sánh thuật toán & ma trận nhầm lẫn.
- **📰 Kho Bài Báo & Chấm Điểm**: Bảng dữ liệu chi tiết có tìm kiếm trực tiếp.

### 2.2. Khai thác chi tiết các cụm biểu đồ:

| Vị trí | Cụm biểu đồ | Ý nghĩa nghiệp vụ |
|---|---|---|
| **Hàng 1** | **5 Thẻ KPI Đo Lường** | • **Kho bài báo CSDL**: Tổng số lượng bài đã thu thập và chuẩn hóa.<br>• **% Tích cực / Trung tính / Tiêu cực**: Tỷ lệ cảm xúc toàn thị trường.<br>• **F1 mô hình AI**: Điểm F1-Score kiểm định của mô hình AI đang chạy (> 0.93). |
| **Hàng 2** | **Cụm 3 Biểu Đồ Cảm Xúc** | • **Donut Chart**: Xem tỷ lệ phần trăm phân bố nhãn cảm xúc.<br>• **Horizontal Bar Chart**: So sánh cảm xúc theo chuyên mục (Kinh tế, Công nghệ, Sức khỏe...).<br>• **Stacked Bar Chart 30 ngày**: Theo dõi số lượng bài báo từng ngày trong tháng qua. |
| **Hàng 3** | **Dự Báo AI 14 Ngày & Từ Khóa** | • **Line Chart AR(1) Forecast**: Đường xanh là số liệu thực tế (trượt 7 ngày); đường tím đứt đoạn là **dự báo 14 ngày tới của AI**; vùng bóng mờ là **khoảng tin cậy 95%**.<br>• **Dropdown Chuyên mục**: Chọn xem riêng dự báo cho từng chuyên mục báo chí.<br>• **Đám mây từ khóa tiếng Việt**: Kích thước từ khóa tỷ lệ thuận với trọng số TF-IDF. |
| **Hàng 4** | **Khung Nhúng Superset Trực Tiếp** | Xem trực tiếp các biểu đồ nâng cao từ máy chủ Apache Superset. Có nút **Tải lại Superset** và nút **Mở Tab Riêng**. |
| **Hàng 5** | **Đánh Giá Mô Hình MLOps** | Bảng so sánh 4 giải thuật (*Lexicon, Naive Bayes, Logistic Regression, Linear SVM*) và 2 ảnh **Ma trận nhầm lẫn (Confusion Matrix)** trên tập Test và 400 bài báo thực tế gán nhãn tay. |
| **Hàng 6** | **Kiến Trúc Dữ Liệu & ETL** | Sơ đồ 5 trạm luồng dữ liệu, bảng mốc nạp tăng dần (**Watermarks**), nhật ký ETL và **Bảng đối chiếu Trước/Sau làm sạch** (minh họa loại bỏ HTML và chuẩn hóa Unicode NFC). |
| **Hàng 7** | **Kho Bài Báo & Chấm Điểm AI** | Danh sách 50 bài mới nhất. Gõ từ khóa vào ô **`🔍 Tìm kiếm tiêu đề hoặc từ khóa...`** để lọc bài viết trực tiếp tức thì (không cần reload trang). |

---

## 3. HƯỚNG DẪN VẬN HÀNH APACHE SUPERSET BI (http://localhost:8088)

Hệ thống Apache Superset chạy độc lập tại cổng `8088` phục vụ quản trị và thiết kế biểu đồ chuyên sâu:
- **Địa chỉ truy cập**: [http://localhost:8088](http://localhost:8088)
- **Tài khoản đăng nhập**: `admin` / `admin`

---

### 3.1. Cơ chế Tự Động Hóa Biểu Đồ (Auto-Import) — Người khác KHÔNG CẦN tạo lại biểu đồ bằng tay!
> **LƯU Ý QUAN TRỌNG:**
> Khi **thầy cô hoặc người khác** tải dự án về máy của họ để chạy:
> - **Họ hoàn toàn KHÔNG CẦN phải tự tạo biểu đồ bằng tay trên Superset nữa.**
> - Lý do: Toàn bộ cấu hình kết nối CSDL, các Datasets, các Chart và giao diện Dashboard đã được đóng gói sẵn trong file di động: **`superset/dashboard_export.zip`**.
> - Lệnh `docker compose up -d` trong file `docker-compose.yml` sẽ **tự động nạp gói này vào Superset**. Người chấm bài chỉ cần mở trang web là thấy toàn bộ biểu đồ hiển thị 100%!

---

### 3.2. Tại sao ban đầu sinh viên phải tự tạo biểu đồ một lần?
1. **Bản chất công cụ BI**: Cơ sở dữ liệu (PostgreSQL) chỉ lưu số liệu và kết quả AI. CSDL không thể tự biết người dùng muốn vẽ biểu đồ hình tròn, biểu đồ cột chồng hay đường dự báo. Cần một nhà phân tích (sinh viên) trực tiếp thiết lập trục X, trục Y, công thức tính và màu sắc trên Superset.
2. **Yêu cầu môn học**: Đánh giá kỹ năng của sinh viên trong việc chuyển đổi dữ liệu thô và kết quả AI thành các biểu đồ trực quan có ý nghĩa nghiệp vụ (Checklist 03 & 04).
3. **Quy trình hoàn chỉnh**: Sau khi sinh viên tự tay thiết kế xong Dashboard trên máy của mình ➔ Hệ thống trích xuất thành file `dashboard_export.zip` để đóng gói thành sản phẩm hoàn chỉnh mang đi nộp bài.

---

### 3.3. Hướng dẫn nếu muốn tự tạo thêm hoặc chỉnh sửa biểu đồ mới

Nếu bạn muốn tạo thêm biểu đồ mới hoặc tùy biến lại giao diện Dashboard:

#### A. Thông tin CSDL & Views đã kết nối sẵn:
- **Tên kết nối**: `News DW` (hoặc `PostgreSQL`)
- **Chuỗi kết nối nội bộ Docker**: `postgresql://superset_reader:superset_reader_123@postgres:5432/news_dw`
- **Schema phân tích**: `analytics`
- **Các Views chính phục vụ Superset**:
  1. `v_article_sentiment`: Dữ liệu chi tiết từng bài (chuyên mục, nguồn, nhãn, điểm số, độ tin cậy).
  2. `v_daily_sentiment`: Tổng hợp số lượng bài theo ngày × chuyên mục × nguồn tin.
  3. `v_sentiment_index_7d`: Chỉ số cảm xúc trung bình trượt 7 ngày.
  4. `v_sentiment_forecast`: Dữ liệu thực tế nối tiếp kết quả dự báo 14 ngày tới.
  5. `v_keyword_trend`: Trọng số từ khóa tiếng Việt phục vụ vẽ Word Cloud.

#### B. Các bước tạo biểu đồ mới:
1. Vào menu **`Datasets`** ➔ Bấm **`+ DATASET`** ➔ Chọn Database: `News DW`, Schema: `analytics`, chọn View tương ứng.
2. Vào menu **`Charts`** ➔ Bấm **`+ CHART`** ➔ Chọn Dataset và loại biểu đồ (Visualization Type).
3. Cấu hình trục X, Dimensions và Metrics, sau đó bấm **Save** và chọn **Add to Dashboard**.

#### C. Cách đóng gói lại file sau khi chỉnh sửa Dashboard:
Nếu bạn vừa chỉnh sửa thêm biểu đồ mới và muốn cập nhật lại file đóng gói `dashboard_export.zip`:
```powershell
docker exec news_dw_superset superset export-dashboards -f /app/pythonpath/dashboard_export.zip
```
File đóng gói sẽ tự động được cập nhật để mang sang bất kỳ máy tính nào khác!


---

## 4. TỔNG QUAN KIẾN TRÚC HỆ THỐNG & DỮ LIỆU

Hệ thống được thiết kế theo chuẩn Enterprise Data Warehouse tích hợp AI và BI hoàn chỉnh:

```
[ NGUỒN TIN TỨC ĐA KÊNH ]
  ├── CMS Tòa soạn nội bộ (SQLite: cms_toasoan.db)
  └── 3 Kênh RSS đối tác (Tin Nhanh 24h, Thời Báo Số, Nhịp Sống Việt)
                    │
                    ▼  (ETL Pipeline - newsai/etl/)
[ CƠ SỞ DỮ LIỆU TRUNG TÂM POSTGRESQL (news_dw) ]
  ├── 1. Schema "etl"       : Watermark nạp tăng dần, category_map, nhật ký etl_run_log
  ├── 2. Schema "staging"   : raw_article lưu JSONB gốc nguyên bản, chống trùng lặp
  ├── 3. Schema "core"      : Mô hình sao chuẩn hóa (dim_source, dim_category, dim_date, article)
  └── 4. Schema "analytics" : Kết quả mô hình AI + 6 SQL Views phục vụ Superset
                    │
                    ▼
[ MODULE TRÍ TUỆ NHÂN TẠO (newsai/ai/) ]
  ├── Phân loại cảm xúc tiếng Việt: So sánh 4 mô hình (Chọn Naive Bayes TF-IDF F1 > 0.94)
  ├── Trích xuất từ khóa: TF-IDF từ ghép tiếng Việt (tự động lọc stopwords)
  └── Dự báo chuỗi thời gian: Mô hình AR(1) Mean-Reverting 14 ngày tới + KTC 95%
                    │
                    ▼
[ LỚP TRỰC QUAN HÓA & RA QUYẾT ĐỊNH ]
  ├── Apache Superset BI Server (Port 8088): Dashboard tự động nạp (Auto-Import)
  └── Web Điều Hành Light Mode (Port 8000): Nhúng trực tiếp toàn bộ biểu đồ & dữ liệu
```

---

## 5. XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `Connection refused: port 5433 failed` | Docker Desktop chưa được bật hoặc chưa chạy `docker compose up -d`. | Mở ứng dụng Docker Desktop trên Windows, chờ trạng thái *Engine running*, sau đó chạy lại lệnh `docker compose up -d`. |
| `ModuleNotFoundError: No module named 'psycopg2'` | Chưa kích hoạt môi trường ảo `.venv` hoặc chưa cài `requirements.txt`. | Chạy lệnh: `.venv\Scripts\activate` rồi chạy `pip install -r requirements.txt`. |
| Khung Superset báo `Refused to connect` | Do trình duyệt chặn Iframe cross-origin nếu chưa cấu hình Talisman. | Dự án đã có sẵn file `superset/superset_config.py`. Hãy chạy `docker compose up -d` để nạp cấu hình, sau đó đăng nhập `http://localhost:8088` 1 lần rồi F5 lại trang 8000. |
| Cổng 8000 hoặc 8088 bị chiếm dụng | Có một tiến trình khác đang dùng cổng. | Đổi cổng khi chạy: `python -m newsai.viewer --port 8081` và mở `http://localhost:8081`. |
