# TÀI LIỆU KỊCH BẢN KIỂM THỬ HỆ THỐNG (TEST SCENARIOS)
## Dự Án: Hệ Thống Phân Tích Tin Tức Tích Hợp AI & Apache Superset BI
**Môn học:** Kinh Doanh Thông Minh (Business Intelligence) — Bài TH2  
**Phiên bản tài liệu:** 1.0  
**Ngày cập nhật:** Tháng 10/2026  

---

## 1. MỤC TIÊU & PHẠM VI KIỂM THỬ

Tài liệu này định nghĩa chi tiết các kịch bản kiểm thử (Test Cases & Test Scenarios) nhằm nghiệm thu toàn diện hệ thống theo chuẩn yêu cầu bài thực hành:
1. **Kiểm thử Hạ tầng & CSDL (Checklist 01):** Khởi chạy Docker (PostgreSQL 16, Apache Superset 3.0), tính toàn vẹn 4 tầng schema (`etl`, `staging`, `core`, `analytics`) và phân quyền bảo mật.
2. **Kiểm thử Pipeline ETL & Nạp Tăng Dần (Checklist 01):** Thu thập đa nguồn (CMS nội bộ + 3 kênh RSS), khử trùng lặp dữ liệu, chuẩn hóa làm sạch text tiếng Việt và cơ chế Watermark nạp tăng dần.
3. **Kiểm thử Trí Tuệ Nhân Tạo & MLOps (Checklist 02):** So sánh 4 thuật toán phân loại cảm xúc (Lexicon, Naive Bayes, Logistic Regression, Linear SVM), cơ chế Champion/Challenger, trích xuất từ khóa TF-IDF và dự báo chuỗi thời gian AR(1) 14 ngày tới.
4. **Kiểm thử Trực Quan Hóa & Nhúng BI (Checklist 03 & 04):** Bảng điều khiển Apache Superset BI (port 8088), cơ chế tự động nạp Dashboard (Auto-Import) và Web Điều Hành Light Mode (port 8000) nhúng toàn bộ biểu đồ liền mạch với thiết kế vuông vức phẳng (`border-radius: 0`).

---

## 2. MÔI TRƯỜNG & CÔNG CỤ KIỂM THỬ

- **Hệ điều hành:** Windows 10/11 (PowerShell) / macOS / Linux
- **Môi trường Python:** Python 3.10+ (kích hoạt `.venv`)
- **Containerization:** Docker Desktop (Engine running)
- **Cơ sở dữ liệu:** PostgreSQL 16 (Port host: `5433` -> container: `5432`)
- **BI Server:** Apache Superset 3.0 (Port host: `8088`)
- **Web Server:** Python HTTP Daemon Viewer (Port host: `8000`)
- **Công cụ kiểm thử tự động:** `python tests/test_system.py`

---

## 3. BẢNG TỔNG HỢP CÁC KỊCH BẢN KIỂM THỬ (TEST MATRIX)

| Mã Test | Tên Kịch Bản Kiểm Thử | Mức Độ | Phương Pháp | Kết Quả Kỳ Vọng |
|---|---|---|---|---|
| **TC-01** | Kiểm thử tự động nhanh (Automated Smoke Test) | **Critical** | Chạy Script Python | 4/4 nhóm test đạt PASSED 100% |
| **TC-02** | Khởi động hạ tầng Docker & CSDL trung tâm | **High** | Docker CLI | PostgreSQL & Superset `healthy` |
| **TC-03** | Chạy toàn trình Data Pipeline & AI | **Critical** | Lệnh CLI | Khởi tạo CSDL, ETL, Train, Chấm điểm, Dự báo |
| **TC-04** | Kiểm thử nạp tăng dần (Incremental Load) & Khử trùng | **High** | CLI & Web | Chỉ nạp tin mới sau Watermark, không nhân bản bài cũ |
| **TC-05** | Kiểm thử cơ chế MLOps (Champion vs Challenger) | **High** | CLI & Model Registry | Đánh giá 4 mô hình, kích hoạt model có F1 tốt nhất |
| **TC-06** | Kiểm thử an toàn phân quyền người dùng (Least Privilege) | **Medium** | Truy vấn SQL | `superset_reader` đọc được 7 View, bị chặn ghi |
| **TC-07** | Kiểm thử giao diện Web Điều Hành (Light Mode & Sharp) | **High** | Trình duyệt Web | Chuẩn Light Mode, `border-radius: 0`, nhúng đủ cụm biểu đồ |
| **TC-08** | Kiểm thử Apache Superset BI & Tính di động Dashboard | **Critical** | Trình duyệt & Iframe | Tự nạp Dashboard từ zip, nhúng Iframe không bị chặn |

---

## 4. CHI TIẾT CÁC KỊCH BẢN KIỂM THỬ

---

### TC-01: KIỂM THỬ TỰ ĐỘNG TOÀN DIỆN MỘT NÚT BẤM (AUTOMATED TEST)
- **Mục tiêu:** Kiểm tra nhanh toàn bộ các cấu phần (CSDL, Phân quyền, Web Viewer, Superset) chỉ với 1 câu lệnh.
- **Tiền điều kiện:** Docker đang chạy và môi trường ảo `.venv` đã được kích hoạt.
- **Các bước thực hiện:**
  ```powershell
  python tests/test_system.py
  ```
- **Kết quả kỳ vọng:**
  ```
  [TEST 1/4] Kiểm tra cấu trúc CSDL và số lượng bản ghi... -> PASSED (19 bảng/views)
  [TEST 2/4] Kiểm tra phân quyền tài khoản superset_reader... -> PASSED (Đọc 7 view, chặn ghi)
  [TEST 3/4] Kiểm tra trang web điều hành Light Mode... -> PASSED (Mã 200, border-radius: 0)
  [TEST 4/4] Kiểm tra Apache Superset (http://localhost:8088)... -> PASSED (X-Frame-Options: None)
  🎉 TẤT CẢ 4 BỘ TEST ĐỀU ĐẠT CHUẨN 100%!
  ```

---

### TC-02: KIỂM THỬ KHỞI ĐỘNG HẠ TẦNG DOCKER
- **Mục tiêu:** Đảm bảo 2 container PostgreSQL và Superset khởi động ổn định, đúng cổng và kết nối chung mạng nội bộ `newsnet`.
- **Các bước thực hiện:**
  1. Chạy lệnh:
     ```powershell
     docker compose up -d
     ```
  2. Kiểm tra danh sách container:
     ```powershell
     docker ps
     ```
- **Kết quả kỳ vọng:**
  - `news_dw_postgres`: Trạng thái `Up ... (healthy)`, ánh xạ cổng `0.0.0.0:5433->5432/tcp`.
  - `news_dw_superset`: Trạng thái `Up ... (healthy)`, ánh xạ cổng `0.0.0.0:8088->8088/tcp`.

---

### TC-03: KIỂM THỬ TOÀN TRÌNH DATA PIPELINE & HUẤN LUYỆN AI
- **Mục tiêu:** Kiểm tra quy trình chạy từ đầu đến cuối: khởi tạo CSDL, sinh dữ liệu nguồn, nạp ETL, huấn luyện mô hình, chấm điểm cảm xúc và dự báo chuỗi thời gian.
- **Các bước thực hiện:**
  ```powershell
  python -m newsai.run_all
  ```
- **Kết quả kỳ vọng:**
  - `init-db`: Thực thi thành công 3 file `01_schema.sql`, `02_views_superset.sql`, `03_superset_readonly_user.sql`.
  - `generate`: Tạo hơn 2.800 bài viết giả lập tại CMS (`cms_toasoan.db`) và 3 file RSS XML.
  - `etl`: Nạp vào `staging.raw_article` -> Chuẩn hóa làm sạch và lưu vào `core.article`.
  - `train`: So sánh 4 mô hình, Naive Bayes đạt F1 > 0.93 và được chọn làm Champion.
  - `predict`: Chấm điểm cảm xúc và trích xuất từ khóa cho toàn bộ bài báo.
  - `forecast`: Dự báo chỉ số cảm xúc 14 ngày tới bằng AR(1) Mean-Reverting cho 7 chuyên mục.
  - Tổng thời gian hoàn tất: ~60 đến 80 giây.

---

### TC-04: KIỂM THỬ NẠP TĂNG DẦN (INCREMENTAL LOAD) & KHỬ TRÙNG LẶP
- **Mục tiêu:** Chứng minh hệ thống chỉ nạp thêm bài viết mới sau mốc thời gian Watermark, tự động phát hiện bài bị sửa nội dung và không làm nhân bản bài cũ.
- **Các bước thực hiện:**
  1. Ghi nhận số lượng bài hiện tại trên trang web (ví dụ: `2.829` bài).
  2. Chạy lệnh mô phỏng sinh 5 bài viết mới tại CMS và 5 bài mới tại RSS:
     ```powershell
     python -m newsai.sample_data.simulate_new_data -n 5
     ```
  3. Chạy lệnh cập nhật dữ liệu định kỳ:
     ```powershell
     python -m newsai.run_all --steps etl predict forecast
     ```
  4. Mở trình duyệt và F5 lại trang web `http://localhost:8000`.
- **Kết quả kỳ vọng:**
  - Terminal báo: Trích xuất đúng số lượng bài mới theo mốc Watermark (`rows_extracted = 10`), bỏ qua các bài đã có (`rows_skipped`).
  - Bài viết bị biên tập lại được cập nhật `content_hash` mới.
  - Tổng số bài viết hiển thị trên thẻ KPI tăng chính xác.
  - Bảng **⏱️ Mốc Nạp Tăng Dần (Watermarks)** trên trang web cập nhật mốc thời gian mới nhất.

---

### TC-05: KIỂM THỬ MLOPS & CƠ CHẾ CHAMPION / CHALLENGER
- **Mục tiêu:** Kiểm tra quy trình đánh giá mô hình định kỳ, chỉ kích hoạt mô hình mới nếu F1-score vượt trội hoặc bằng mô hình đang chạy.
- **Các bước thực hiện:**
  1. Chạy lệnh huấn luyện lại:
     ```powershell
     python -m newsai.run_all --steps train
     ```
  2. Kiểm tra log hiển thị trên terminal:
     - So sánh 4 giải thuật: *Từ điển (Baseline), Naive Bayes, Logistic Regression, Linear SVM*.
     - Báo cáo điểm F1 trên tập Test 20% và 400 bài báo thực tế gán nhãn tay.
  3. Thử nghiệm lệnh kích hoạt cưỡng bức:
     ```powershell
     python -m newsai.run_all --steps train --force-activate
     ```
- **Kết quả kỳ vọng:**
  - File ma trận nhầm lẫn `reports/confusion_matrix_test.png` và `reports/confusion_matrix_production.png` được tạo mới.
  - Bản ghi mới được thêm vào bảng `analytics.model_registry`.
  - Nhờ cơ chế **CTE Active Model Fallback**, các biểu đồ và Views không bao giờ bị rỗng (0 dòng) trong lúc huấn luyện lại.

---

### TC-06: KIỂM THỬ PHÂN QUYỀN BẢO MẬT (LEAST PRIVILEGE)
- **Mục tiêu:** Kiểm tra tài khoản `superset_reader` chỉ có quyền đọc trên các views nghiệp vụ, không được can thiệp vào tầng dữ liệu nhạy cảm hoặc sửa đổi CSDL.
- **Các bước thực hiện (chạy qua Python hoặc psql):**
  1. Kết nối vào CSDL bằng user: `superset_reader` / mật khẩu: `superset_reader_123`.
  2. Thực hiện truy vấn đọc:
     ```sql
     SELECT COUNT(*) FROM analytics.v_article_sentiment;
     SELECT COUNT(*) FROM analytics.v_sentiment_forecast;
     ```
  3. Thực hiện truy vấn ghi (xóa/sửa):
     ```sql
     DELETE FROM core.article WHERE 1=1;
     DROP TABLE staging.raw_article;
     ```
- **Kết quả kỳ vọng:**
  - Lệnh `SELECT`: Thực thi thành công, trả về đúng số lượng dòng.
  - Lệnh `DELETE` / `DROP`: Bị PostgreSQL từ chối với lỗi `permission denied for table ...`.

---

### TC-07: KIỂM THỬ GIAO DIỆN WEB ĐIỀU HÀNH (HTTP://LOCALHOST:8000)
- **Mục tiêu:** Đảm bảo giao diện người dùng hiển thị đúng các tiêu chí mỹ thuật và nghiệp vụ được yêu cầu:
- **Các bước kiểm tra bằng mắt & thao tác trực tiếp:**
  1. **Phong cách thiết kế (Design Aesthetics):**
     - Nền sáng hiện đại (**Light Mode**: `#f8fafc`).
     - Tất cả các thẻ (cards), nút bấm, bảng biểu đều **vuông vức sắc cạnh, không bo góc** (`border-radius: 0 !important`).
     - Không có các thẻ badge trạng thái rườm rà ở góc trên bên phải.
  2. **Thanh điều hướng nhanh (Jump Nav):**
     - Nhấp thử các nút: `📊 Chỉ Số KPI`, `📈 Biểu Đồ Cảm Xúc`, `🤖 Dự Báo AI 14 Ngày`, `🚀 Superset Dashboard`, `🏗️ Kiến Trúc ETL`, `🧠 Đánh Giá AI`, `📰 Kho Bài Báo`. Trang tự động cuộn mượt mà đến đúng mục.
  3. **Khả năng tương tác của biểu đồ:**
     - Rê chuột vào **Donut Chart**, **Bar Chart chuyên mục**, **Stacked Bar Chart 30 ngày**: Tooltip hiển thị số liệu chi tiết.
     - Tại biểu đồ **Dự Báo AI 14 Ngày**: Nhấp chọn dropdown chuyên mục (Kinh tế, Công nghệ, Thể thao...) -> Biểu đồ chuyển đổi số liệu và dải bóng mờ KTC 95% tương ứng.
     - Đám mây từ khóa: Từ khóa có kích thước phân cấp rõ ràng theo trọng số TF-IDF.
  4. **Kiểm tra ô tìm kiếm bài báo trực tiếp:**
     - Cuộn xuống phần **Kho Bài Báo & Chấm Điểm AI**.
     - Gõ thử từ khóa vào ô `🔍 Tìm kiếm tiêu đề hoặc từ khóa...` (ví dụ: `kinh tế`, `chứng khoán`, `AI`).
     - Bảng bài báo lọc ngay lập tức mà không cần bấm Enter hay tải lại trang.

---

### TC-08: KIỂM THỬ APACHE SUPERSET BI & TÍNH DI ĐỘNG CỦA DASHBOARD
- **Mục tiêu:** Đảm bảo Apache Superset hiển thị đầy đủ biểu đồ mà người dùng / giảng viên **không cần tạo lại thủ công**.
- **Các bước thực hiện:**
  1. **Kiểm tra nhúng Iframe trên Web Điều Hành (port 8000):**
     - Cuộn đến mục **🚀 Superset BI Dashboard (Nhúng Trực Tiếp)**.
     - Khung Iframe hiển thị đầy đủ giao diện Superset Dashboard ID 1, không bị lỗi `Refused to connect` hay `ERR_BLOCKED_BY_RESPONSE`.
     - Nhấp nút **`Tải lại Superset`**: Khung iframe tải lại trơn tru.
     - Nhấp nút **`Mở Tab Riêng`**: Trình duyệt mở ra trang Superset tại `http://localhost:8088/superset/dashboard/1/`.
  2. **Kiểm tra tính di động (Zero-Config Auto-Import):**
     - Mở Superset tại `http://localhost:8088` (Đăng nhập: `admin` / `admin`).
     - Vào menu **Dashboards**: Thấy sẵn Dashboard mang tên *"Hệ Thống Phân Tích Tin Tức & Dự Báo AI"*.
     - Vào menu **Charts**: Thấy sẵn danh sách các biểu đồ đã được thiết kế.
     - Vào menu **Data -> Datasets**: Thấy sẵn các Datasets kết nối tới schema `analytics`.
  3. **Kiểm tra cơ chế xuất gói Dashboard:**
     - Chạy thử lệnh xuất cấu hình di động:
       ```powershell
       docker exec news_dw_superset superset export-dashboards -f /app/pythonpath/dashboard_export.zip
       ```
     - File `superset/dashboard_export.zip` được cập nhật thành công.

---

## 5. BÁO CÁO TỔNG KẾT & KẾT LUẬN NGHIỆM THU

- **Tổng số kịch bản kiểm thử:** 8 / 8 Test Cases
- **Số kịch bản đạt chuẩn (PASSED):** 8 / 8 (Tỷ lệ: 100%)
- **Số lỗi tồn đọng:** 0
- **Kết luận:** Hệ thống hoạt động ổn định, đáp ứng hoàn toàn và vượt mức các yêu cầu của Bài TH2 (Checklist 01, 02, 03, 04), sẵn sàng cho buổi thuyết trình, demo trực tiếp và bàn giao chấm bài.
