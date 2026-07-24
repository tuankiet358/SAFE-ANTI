"""
cogs/anti/constants.py — Hằng số, ngưỡng cấu hình và brand tokens riêng cho module SAFE-ANTI 2.0.
Không import bất kỳ thành phần nội bộ nào của module để tránh circular import.
"""

import os

# ─────────────────────────────────────────────────────────────────────────
# DATABASE PATH
# ─────────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_PATH  = os.path.join(_BASE_DIR, "database", "anti_settings.db")

# ─────────────────────────────────────────────────────────────────────────
# BRAND TOKENS
# ─────────────────────────────────────────────────────────────────────────
_BRAND   = "SAFE-ANTI 2.0"
_DIVIDER = "─────────────────────────────"

# Tên định danh cho AutoMod rules — dùng để tìm kiếm/xóa rules khi tắt module
_AUTOMOD_RULE_ANTILINK = f"[{_BRAND}] Anti-Link AutoMod"
_AUTOMOD_RULE_ANTISPAM = f"[{_BRAND}] Anti-Spam AutoMod"

# ─────────────────────────────────────────────────────────────────────────
# MÀU SẮC THƯƠNG HIỆU
# ─────────────────────────────────────────────────────────────────────────
_CLR_SUCCESS  = 0x2ECC71   # Xanh lá — hoạt động / bật
_CLR_DANGER   = 0xE74C3C   # Đỏ — nguy hiểm / tắt / lỗi
_CLR_ALERT    = 0xFF4500   # Đỏ cam — cảnh báo khẩn cấp
_CLR_LOCKDOWN = 0xFF0000   # Đỏ thuần — lockdown toàn server
_CLR_PURGE    = 0xFF6600   # Cam — phát hiện link-spam
_CLR_TIMEOUT  = 0x95A5A6   # Xám — menu hết hạn
_CLR_PHASE1   = 0xF39C12   # Vàng cam — giai đoạn 1 phát hiện
_CLR_PHASE2   = 0xE67E22   # Cam đậm — giai đoạn 2 xử lý
_CLR_BYPASS   = 0x8B0000   # Đỏ tối — cảnh báo bypass hierarchy
_CLR_AUTOMOD  = 0x5865F2   # Xanh Discord — AutoMod action log
_CLR_BOT_RAID = 0x9B59B6   # Tím — cảnh báo bot raid
_CLR_MENTION  = 0xC0392B   # Đỏ đậm — anti mass mention
_CLR_AGE      = 0x1ABC9C   # Ngọc — account age filter
_CLR_WEBHOOK  = 0x8E44AD   # Tím đậm — anti webhook
_CLR_EMOJI    = 0xF1C40F   # Vàng — anti emoji/sticker spam
_CLR_RENAME   = 0x2980B9   # Xanh dương — anti channel rename
_CLR_WARN_CH  = 0xFF4500   # Đỏ cam — embed cảnh báo gửi tại kênh vi phạm

# ─────────────────────────────────────────────────────────────────────────
# CUSTOM EMOJI (giữ nguyên ID gốc)
# ─────────────────────────────────────────────────────────────────────────
_ICO_SHIELD = "<:khien:1522083687645319278>"
_ICO_LINK   = "<:link:1522569128760709190>"
_ICO_CHAT   = "<:chat:1521762991677247608>"
_ICO_STOP   = "<:stop:1521777358485327872>"
_ICO_TICK   = "<:tick1:1521715162283774013>"
_ICO_RESULT = "<:ketqua:1521763310658261163>"
_ICO_TIME   = "<a:time:1522029202323406928>"
_ICO_LOCK   = "<a:khoa:1522079387820752977>"
_ICO_PLAY   = "<:choi:1522032415281905786>"

# ─────────────────────────────────────────────────────────────────────────
# NGƯỠNG CẤU HÌNH SAFE-ANTI 2.0
# ─────────────────────────────────────────────────────────────────────────
_MASS_MENTION_THRESHOLD   = 3    # > 3 user/role mention trong 1 tin → timeout
_MASS_MENTION_TIMEOUT_MIN = 30   # Timeout 30 phút
_ACCOUNT_AGE_DAYS         = 7    # Tài khoản < 7 ngày → timeout đến đủ 7 ngày
_EMOJI_SPAM_THRESHOLD     = 7    # > 7 emoji/sticker trong 1 tin → timeout
_EMOJI_TIMEOUT_MIN        = 15   # Timeout 15 phút
