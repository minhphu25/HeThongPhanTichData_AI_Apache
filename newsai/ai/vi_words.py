"""Tách từ tiếng Việt cho bước trích xuất từ khóa.

Tiếng Việt viết cách theo âm tiết ("lãi suất" = 2 âm tiết, 1 từ) nên không thể tách từ bằng dấu cách.
- Nếu máy có thư viện underthesea (pip install underthesea) -> dùng word_tokenize của underthesea.
- Nếu không -> thuật toán "khớp dài nhất" (longest matching) với từ điển thuật ngữ báo chí dưới đây.
"""
from functools import lru_cache

NEWS_TERMS = """
ngân hàng|nhà nước|ngân hàng nhà nước|thị trường|chứng khoán|thị trường chứng khoán|giá vàng|xuất khẩu|nông sản
doanh nghiệp|bất động sản|lãi suất|cho vay|dệt may|xăng dầu|đầu tư|nước ngoài|vốn đầu tư|bán lẻ|du lịch|kim ngạch
thủy sản|tăng trưởng|kỷ lục|kế hoạch|phục hồi|tích cực|trầm lắng|lợi nhuận|khởi sắc|rõ rệt|tin vui|quốc tế|bứt phá
ngoạn mục|thiếu vốn|hỗ trợ|gói hỗ trợ|sụt giảm|đối mặt|nguy cơ|thua lỗ|kéo dài|lao dốc|liên tiếp|đơn hàng|nợ xấu
lo ngại|thiệt hại|nặng nề|khủng hoảng|thanh khoản|kỳ vọng|cảnh báo|rủi ro|vỡ nợ|vốn hóa|số liệu|điều chỉnh|quy định
hội nghị|tổng kết|dự kiến|họp bàn|giao dịch|phiên giao dịch|báo cáo|định kỳ|ý kiến|dự thảo|nghị định|danh sách|hội chợ
công nghệ|khởi nghiệp|ứng dụng|thanh toán|di động|thanh toán di động|điện thoại|phần mềm|trí tuệ nhân tạo|tạo sinh
điện toán|đám mây|điện toán đám mây|dịch vụ|bán dẫn|thương mại điện tử|người dùng|mạng xã hội|ví điện tử|ngân hàng số
gọi vốn|thành công|đánh giá|mở rộng|giải thưởng|đổi mới sáng tạo|phủ sóng|tỉnh thành|ấn tượng|ra mắt|tính năng
chờ đợi|vinh danh|tấn công mạng|rò rỉ|dữ liệu|rò rỉ dữ liệu|sự cố|gián đoạn|diện rộng|vi phạm|quyền riêng tư|sa thải
hàng loạt|nhân viên|phàn nàn|nghiêm trọng|lừa đảo|trực tuyến|lừa đảo trực tuyến|thương vụ|thất bại|tẩy chay|thu thập
trái phép|lộ trình|cập nhật|sự kiện|giới thiệu|sản phẩm|điều khoản|sử dụng|thử nghiệm|triển lãm|khu vực|phiên bản
bảo trì|hệ thống|mạng 5g|đội tuyển|bóng đá|việt nam|câu lạc bộ|hà nội|vận động viên|điền kinh|bóng chuyền|tay vợt
quốc gia|đoàn thể thao|huấn luyện viên|kình ngư|chiến thắng|thuyết phục|huy chương|huy chương vàng|chung kết
vòng chung kết|thi đấu|xuất sắc|khen ngợi|lội ngược dòng|giải đấu|vô địch|trình diễn|đáng tiếc|vòng bảng|chấn thương
dài hạn|sân nhà|thất vọng|người hâm mộ|phong độ|treo giò|tập trung|tập huấn|bốc thăm|chia bảng|lịch thi đấu|họp báo
trận đấu|chuẩn bị|mùa giải|hội quân|kỳ nghỉ|học sinh|giáo dục|đào tạo|giáo dục và đào tạo|đại học|kỳ thi|tốt nghiệp
giáo viên|vùng cao|chương trình|phổ thông|sinh viên|năm nhất|trường học|ngoại ngữ|mầm non|cơ sở vật chất|hiện đại
học bổng|toàn phần|du học|kết quả|mong đợi|tăng lương|phụ huynh|ủng hộ|bảng xếp hạng|châu á|trầm trọng|phản ánh
lạm thu|lộ đề|đề thi|xuống cấp|an toàn|mất an toàn|bỏ học|áp lực|quá tải|phản đối|gay gắt|lịch thi|năm học|tuyển sinh
thông tư|khai giảng|bệnh viện|trung ương|y tế|bác sĩ|tiêm chủng|bệnh nhân|ung thư|sốt xuất huyết|bảo hiểm y tế
phòng khám|tư nhân|điều trị|trẻ em|vùng sâu|phẫu thuật|hiếm gặp|chữa khỏi|hoàn toàn|cấp phép|hy vọng|khám chữa bệnh
miễn phí|kỹ thuật|tiên tiến|chất lượng|người bệnh|bùng phát|vật tư|thuốc giả|sự cố y khoa|tử vong|thái độ|kịp thời
phòng bệnh|sức khỏe|phác đồ|hội thảo|chuyên đề|danh mục|khuyến cáo|người dân|theo dõi|miền trung|giao thông|cứu hộ
dự án|vành đai|đường vành đai|công nhân|khu công nghiệp|chính quyền|địa phương|tình nguyện viên|khu dân cư|ven sông
cơ quan chức năng|chung tay|giúp đỡ|khó khăn|tiến độ|cải thiện|khen thưởng|dũng cảm|mưa bão|thu nhập|giải cứu|mắc kẹt
bão lũ|ùn tắc|lãng phí|mất việc|ngập lụt|bức xúc|ô nhiễm|môi trường|ô nhiễm môi trường|tai nạn|thảm khốc|phương án
phân luồng|cắt điện|cử tri|tiếp xúc cử tri|quy hoạch|ban hành|phòng chống|thiên tai|mùa mưa|kiểm tra|chuyên gia
dư luận|hệ lụy|phân tích|giới phân tích|trách nhiệm|quản lý|thành tích|cơ hội|phóng viên|độc giả|tín hiệu|xu hướng
""".replace("\n", "|")

# Từ ghép quá chung chung, không mang thông tin -> không dùng làm từ khóa
GENERIC = {"thông tin", "cho biết", "theo dõi", "tiếp tục", "liên quan", "nội dung", "chi tiết", "kết quả",
           "dự kiến", "cập nhật", "đánh giá", "chuyên gia", "phóng viên", "độc giả", "tín hiệu", "hoàn toàn",
           "nghiêm trọng", "kéo dài", "năm nay", "dư luận", "giới phân tích", "phân tích", "xu hướng", "cơ hội"}

VOCAB = {w.strip() for w in NEWS_TERMS.split("|") if w.strip()}
MAX_LEN = max(len(w.split()) for w in VOCAB)


@lru_cache(maxsize=1)
def _underthesea():
    try:
        from underthesea import word_tokenize  # type: ignore
        return word_tokenize
    except Exception:
        return None


def segment(text):
    """Trả về danh sách từ (từ ghép giữ dấu cách bên trong, vd: 'lãi suất')."""
    tok = _underthesea()
    if tok is not None:
        try:
            return [w.lower() for w in tok(text)]
        except Exception:
            pass
    syl = text.lower().split()
    out, i = [], 0
    while i < len(syl):
        for n in range(min(MAX_LEN, len(syl) - i), 1, -1):
            cand = " ".join(syl[i:i + n])
            if cand in VOCAB:
                out.append(cand)
                i += n
                break
        else:
            out.append(syl[i])
            i += 1
    return out
