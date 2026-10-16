"""Tiền xử lý văn bản tiếng Việt + mô hình nền (baseline) dựa trên từ điển cảm xúc."""
import re
import unicodedata

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Từ dừng tiếng Việt (rút gọn) - dùng khi trích xuất từ khóa
STOPWORDS = set("""
và của là có được cho với các những một này đó khi đã đang sẽ thì mà để từ tại trong ngoài trên dưới
theo về như nhiều rất cũng vẫn còn lại ra vào nên nếu vì do bị bởi hơn nhất đến tới sau trước qua
ngày tháng năm tuần nay hôm qua chiều sáng tối người đây kia ấy nào gì ai thêm vừa mới các những
tiếp tục liên quan thông tin cho biết ghi nhận theo dõi được xem nội dung chi tiết
""".split())

POSITIVE_WORDS = ["tăng trưởng", "kỷ lục", "vượt", "phục hồi", "tích cực", "lợi nhuận", "khởi sắc", "tin vui",
                  "thành công", "đánh giá cao", "giải thưởng", "ấn tượng", "chiến thắng", "huy chương", "vô địch",
                  "xuất sắc", "hỗ trợ", "hiện đại", "học bổng", "hoan nghênh", "đáng mừng", "cơ hội", "chữa khỏi",
                  "hy vọng", "cải thiện", "khen", "dũng cảm", "giải cứu", "giúp đỡ", "bứt phá", "ủng hộ", "vinh danh"]
NEGATIVE_WORDS = ["giảm", "thua lỗ", "lao dốc", "gặp khó", "nợ xấu", "thiệt hại", "khủng hoảng", "không đạt",
                  "rủi ro", "tấn công", "rò rỉ", "sự cố", "phạt", "sa thải", "phàn nàn", "lừa đảo", "thất bại",
                  "bị loại", "chấn thương", "thất vọng", "thiếu", "lạm thu", "lộ đề", "xuống cấp", "bỏ học",
                  "quá tải", "phản đối", "bùng phát", "thuốc giả", "tử vong", "kém", "ùn tắc", "chậm tiến độ",
                  "mất việc", "ngập lụt", "bức xúc", "ô nhiễm", "tai nạn", "lo ngại", "xấu đi", "nghiêm trọng"]


def normalize(text):
    """Chuẩn hóa Unicode NFC, chữ thường, bỏ dấu câu, gộp khoảng trắng (giữ nguyên dấu tiếng Việt)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def build_input(title, summary):
    """Văn bản đưa vào mô hình: tiêu đề (mang ý chính) + tóm tắt."""
    return f"{normalize(title)} ||| {normalize(summary)}"


def keyword_analyzer(text):
    """Ứng viên từ khóa = các TỪ GHÉP (>= 2 âm tiết) sau khi tách từ tiếng Việt, bỏ từ dừng / từ quá chung."""
    from .vi_words import GENERIC, segment
    words = segment(normalize(text))
    return [w for w in words if " " in w and w not in GENERIC and w not in STOPWORDS]


class LexiconSentiment(BaseEstimator, ClassifierMixin):
    """Mô hình nền: đếm từ tích cực/tiêu cực (tiêu đề nhân hệ số 2). Không cần huấn luyện."""

    def __init__(self, title_weight=2.0):
        self.title_weight = title_weight

    def fit(self, X, y=None):
        self.classes_ = np.array(["negative", "neutral", "positive"])
        return self

    def _score(self, text):
        title, _, rest = text.partition(" ||| ")  # build_input() ghép tiêu đề và tóm tắt bằng ' ||| '
        def s(t):
            return sum(t.count(w) for w in POSITIVE_WORDS) - sum(t.count(w) for w in NEGATIVE_WORDS)
        return self.title_weight * s(title) + s(rest)

    def predict_proba(self, X):
        out = []
        for text in X:
            sc = self._score(text)
            p = np.exp(np.array([-1.5 * sc, 0.75, 1.5 * sc]))  # điểm 0 -> trung tính
            out.append(p / p.sum())
        return np.array(out)

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(axis=1)]
