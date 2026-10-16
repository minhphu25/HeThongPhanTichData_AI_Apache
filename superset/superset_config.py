import os

# Cho phép nhúng iframe từ bên ngoài (tắt chặn X-Frame-Options và CSP)
TALISMAN_ENABLED = False
HTTP_HEADERS = {}

# Bật tính năng nhúng
FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True
}

# Cho phép xem dưới quyền Public/Gamma khi nhúng vào giao diện web
PUBLIC_ROLE_LIKE = "Gamma"

# Cấu hình cookie phù hợp cho iframe trên localhost
SESSION_COOKIE_SAMESITE = "Lax"
ENABLE_PROXY_FIX = True
