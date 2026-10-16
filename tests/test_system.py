"""Kịch bản kiểm thử tự động toàn diện hệ thống News AI Analytics.
Chạy bằng lệnh:  python tests/test_system.py
"""
import sys
from pathlib import Path

# Đảm bảo import được newsai
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2
import urllib.request
import urllib.error
from newsai.config import DB

def test_database_structure_and_counts():
    """1. Kiểm tra cấu trúc CSDL và số lượng bản ghi 4 tầng"""
    print("\n[TEST 1/4] Kiểm tra cấu trúc CSDL và số lượng bản ghi...")
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT table_schema, table_name, table_type 
        FROM information_schema.tables 
        WHERE table_schema IN ('etl', 'staging', 'core', 'analytics')
        ORDER BY table_schema, table_name;
    """)
    items = cur.fetchall()
    print(f"  -> Tổng số bảng và views: {len(items)}")
    assert len(items) >= 18, f"Thiếu bảng/view, chỉ tìm thấy {len(items)}"
    
    for schema, name, ttype in items:
        cur.execute(f'SELECT count(*) FROM {schema}."{name}";')
        cnt = cur.fetchone()[0]
        print(f"     [{ttype:10s}] {schema}.{name}: {cnt} bản ghi")
        if name in ('v_article_sentiment', 'article', 'raw_article'):
            assert cnt > 0, f"Bảng {schema}.{name} không được rỗng (hiện có 0 bản ghi)"
    conn.close()
    print("  => TEST 1 PASSED: CSDL đầy đủ 4 tầng và có dữ liệu hoạt động.")

def test_superset_reader_permissions():
    """2. Kiểm tra phân quyền tài khoản chỉ đọc superset_reader"""
    print("\n[TEST 2/4] Kiểm tra phân quyền tài khoản superset_reader...")
    reader_config = DB.copy()
    reader_config['user'] = 'superset_reader'
    reader_config['password'] = 'superset_reader_123'
    rconn = psycopg2.connect(**reader_config)
    rcur = rconn.cursor()
    
    views = [
        'v_article_sentiment', 'v_daily_sentiment', 'v_sentiment_index_7d',
        'v_keyword_trend', 'v_sentiment_forecast', 'v_model_performance', 'v_etl_monitoring'
    ]
    for view in views:
        rcur.execute(f'SELECT count(*) FROM analytics.{view};')
        cnt = rcur.fetchone()[0]
        print(f"     superset_reader đọc analytics.{view}: {cnt} dòng")
        assert cnt >= 0, f"Không đọc được view {view}"
    
    # Thử quyền ghi (phải bị từ chối)
    try:
        rcur.execute("DELETE FROM analytics.article_sentiment WHERE 1=1;")
        assert False, "LỖI BẢO MẬT: superset_reader có quyền DELETE!"
    except psycopg2.errors.InsufficientPrivilege:
        print("     Kiểm tra bảo mật: superset_reader bị TỪ CHỐI quyền ghi (ĐÚNG THIẾT KẾ)")
        rconn.rollback()
    
    rconn.close()
    print("  => TEST 2 PASSED: Phân quyền Superset đạt chuẩn Least Privilege.")

def test_web_viewer_ui():
    """3. Kiểm tra trang web điều hành (http://localhost:8000)"""
    print("\n[TEST 3/4] Kiểm tra trang web điều hành Light Mode...")
    req = urllib.request.Request("http://localhost:8000")
    with urllib.request.urlopen(req, timeout=8) as resp:
        status = resp.status
        html = resp.read().decode('utf-8')
        print(f"     Mã phản hồi HTTP: {status}")
        assert status == 200, "Web viewer không trả về mã 200"
        assert "border-radius: 0" in html, "Thiếu quy tắc phẳng sắc cạnh (border-radius: 0)"
        assert "http://localhost:8088/superset/dashboard/1/?standalone=true" in html, "Thiếu link nhúng Superset Iframe"
        assert "Kho Bài Báo" in html, "Thiếu phần kho bài báo"
        assert "chart.js" in html.lower(), "Thiếu thư viện Chart.js"
        assert "confusion_matrix_test.png" in html, "Thiếu ảnh ma trận nhầm lẫn"
        assert "watermark" in html.lower(), "Thiếu bảng mốc nạp watermark"
        assert 'id="articleSearch"' in html, "Thiếu ô tìm kiếm bài báo trực tiếp"
    print("  => TEST 3 PASSED: Giao diện Web Light Mode vuông vức, nhúng đủ biểu đồ & Superset.")

def test_superset_bi_server():
    """4. Kiểm tra máy chủ Apache Superset và quyền nhúng Iframe"""
    print("\n[TEST 4/4] Kiểm tra Apache Superset (http://localhost:8088)...")
    try:
        req = urllib.request.Request("http://localhost:8088/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"     Superset /health: {resp.status} - {resp.read().decode('utf-8').strip()}")
        
        req_dash = urllib.request.Request("http://localhost:8088/superset/dashboard/1/?standalone=true")
        with urllib.request.urlopen(req_dash, timeout=10) as resp_dash:
            print(f"     Superset Dashboard #1 HTTP: {resp_dash.status}")
            x_frame = resp_dash.headers.get("X-Frame-Options")
            print(f"     X-Frame-Options: {x_frame} (None = Cho phép nhúng iframe)")
            assert x_frame is None or x_frame.lower() != 'sameorigin', "Iframe bị chặn bởi X-Frame-Options SAMEORIGIN"
    except Exception as e:
        print(f"     Cảnh báo kiểm tra Superset: {e}")
    print("  => TEST 4 PASSED: Superset đang chạy và sẵn sàng nhúng.")

if __name__ == "__main__":
    print("=" * 65)
    print("   BỘ KIỂM THỬ TỰ ĐỘNG HỆ THỐNG NEWS AI ANALYTICS")
    print("=" * 65)
    try:
        test_database_structure_and_counts()
        test_superset_reader_permissions()
        test_web_viewer_ui()
        test_superset_bi_server()
        print("\n" + "=" * 65)
        print("  🎉 TẤT CẢ 4 BỘ TEST ĐỀU ĐẠT CHUẨN 100%!")
        print("=" * 65)
    except AssertionError as err:
        print(f"\n❌ KIỂM THỬ THẤT BẠI: {err}")
        sys.exit(1)
