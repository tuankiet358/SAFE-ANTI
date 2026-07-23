import re
import os
import typing
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
import time

from config import logger
from database import (
    update_anti_db, get_anti_setting
)
from global_cooldown import server_anti_nuke_limiter

# =========================================================================
# HỆ THỐNG BẢO VỆ SERVER — SAFE-ANTI 2.0
# Bao gồm: Discord AutoMod API cho anti-spam/link, on_guild events anti-nuke,
# và menu điều khiển bật/tắt hệ thống Anti qua Select Menu.
#
# [AUTOMOD] Tích hợp Discord AutoMod API thay thế on_message gateway flooding:
#   - Anti Link  → AutoMod rule loại keyword chặn URL + discord.gg invite
#   - Anti Spam  → AutoMod rule loại mention_spam/message_spam chặn mention đồng loạt
#   - Khi bật/tắt module qua Select Menu, bot tự tạo/xóa AutoMod rule tương ứng
#   - on_automod_action_execution nhận callback từ Discord để ghi log đa giai đoạn
#
# [ANTINUKE] GlobalRateLimiter (server_anti_nuke_limiter) phát hiện tấn công
# phân tán (multi-threaded self-bot nuking) mà không cần Audit Log.
# Khi phát hiện, _trigger_lockdown() được gọi ngay lập tức để khóa server,
# sau đó Audit Log vẫn được dùng như biện pháp phụ để truy tìm thủ phạm.
#
# [RACE CONDITION] GlobalRateLimiter và _lockdown_lock dùng asyncio.Lock —
# tất cả lời gọi is_rate_limited() và reset() phải dùng await.
#
# [MEMORY LEAK] Background task dọn dẹp _link_spam_events mỗi 5 phút.
# Giải phóng triệt để key channel_id rác, user timestamps, bot join events,
# channel rename cache — đảm bảo không tích lũy theo thời gian.
#
# [LOG ĐA GIAI ĐOẠN]
#   Giai đoạn 1 — Phát hiện tấn công (cảnh báo ĐANG PHÁT HIỆN)
#   Giai đoạn 2 — Trong quá trình xử lý (cập nhật trạng thái từng bước)
#   Giai đoạn 3 — Hoàn tất (embed tổng kết, hướng dẫn phục hồi)
#
# [HIERARCHY BYPASS] Khi kẻ tấn công có role >= Bot, bot lập tức tag Owner
# và kích hoạt lockdown mức cao nhất thay vì kick/ban trực tiếp.
#
# ─────────────────────────────────────────────────────────────────────────
# SAFE-ANTI 2.0 — TÍNH NĂNG MỚI
# ─────────────────────────────────────────────────────────────────────────
# [ANTI-MASS MENTION] Tin nhắn tag > 3 user/role → Xóa + Timeout 30 phút
# [ACCOUNT AGE FILTER] Tài khoản < 7 ngày khi join → Timeout đến đủ 7 ngày
# [ANTI-WEBHOOK] Webhook mới được tạo → Tự động xóa ngay (trừ Owner/Bot)
# [ANTI-EMOJI/STICKER SPAM] > 10 emoji hoặc sticker → Xóa + Timeout 15 phút
# [ANTI-CHANNEL RENAME] Đổi tên/topic kênh → Khôi phục + Tước Manage Channels
# =========================================================================

# ─────────────────────────────────────────────────────────────────────────
# DATABASE PATH — trỏ đúng vào thư mục database/ từ thư mục gốc dự án
# ─────────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH  = os.path.join(_BASE_DIR, "database", "anti_settings.db")

# ─────────────────────────────────────────────────────────────────────────
# CONSTANTS — SAFE-ANTI 2.0 BRAND TOKENS
# ─────────────────────────────────────────────────────────────────────────
_BRAND       = "SAFE-ANTI 2.0"
_DIVIDER     = "─────────────────────────────"

# Tên định danh cho AutoMod rules — dùng để tìm kiếm/xóa rules khi tắt module
_AUTOMOD_RULE_ANTILINK = f"[{_BRAND}] Anti-Link AutoMod"
_AUTOMOD_RULE_ANTISPAM = f"[{_BRAND}] Anti-Spam AutoMod"

# Màu sắc thương hiệu
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

# Custom emoji (giữ nguyên ID gốc)
_ICO_SHIELD   = "<:khien:1522083687645319278>"
_ICO_LINK     = "<:link:1522569128760709190>"
_ICO_CHAT     = "<:chat:1521762991677247608>"
_ICO_STOP     = "<:stop:1521777358485327872>"
_ICO_TICK     = "<:tick1:1521715162283774013>"
_ICO_RESULT   = "<:ketqua:1521763310658261163>"
_ICO_TIME     = "<a:time:1522029202323406928>"
_ICO_LOCK     = "<a:khoa:1522079387820752977>"
_ICO_PLAY     = "<:choi:1522032415281905786>"

# ─────────────────────────────────────────────────────────────────────────
# SAFE-ANTI 2.0 — NGƯỠNG CẤU HÌNH
# ─────────────────────────────────────────────────────────────────────────
_MASS_MENTION_THRESHOLD   = 3      # > 3 user/role mention trong 1 tin → timeout
_MASS_MENTION_TIMEOUT_MIN = 30     # Timeout 30 phút
_ACCOUNT_AGE_DAYS         = 7      # Tài khoản < 7 ngày → timeout đến đủ 7 ngày
_EMOJI_SPAM_THRESHOLD     = 7     # > 10 emoji/sticker trong 1 tin → timeout
_EMOJI_TIMEOUT_MIN        = 15     # Timeout 15 phút


# ─────────────────────────────────────────────────────────────────────────
# HELPER: BADGE TRẠNG THÁI INLINE
# ─────────────────────────────────────────────────────────────────────────
def _status_badge(active: bool) -> str:
    return "`● ACTIVE`" if active else "`○ OFFLINE`"


# ─────────────────────────────────────────────────────────────────────────
# HELPER: TÌM LOG CHANNEL (anti → log → public_updates → system → fallback)
# ─────────────────────────────────────────────────────────────────────────
def _get_log_channel(guild: discord.Guild) -> typing.Optional[discord.TextChannel]:
    """
    Trả về channel dùng để gửi log bảo mật.

    Chiến lược tìm kiếm theo thứ tự ưu tiên:
      1. Bất kỳ text channel nào có tên chứa "anti" — ưu tiên cao nhất.
      2. Bất kỳ text channel nào có tên chứa "log" — ưu tiên thứ hai.
      3. guild.public_updates_channel (Community Updates Channel) — fallback.
      4. guild.system_channel — kênh hệ thống mặc định của Discord.
      5. Fallback cuối: kênh text đầu tiên mà bot có quyền send_messages.
    """
    _ANTI_KEYWORDS = ("anti", "moderator-only", "moderator")
    _LOG_KEYWORDS  = ("log", "moderator-only", "moderator")

    if guild.me is None:
        logger.warning(
            f"[AntiCog][_get_log_channel] guild.me is None tại guild {guild.id} — "
            f"bot chưa load xong, bỏ qua tìm log channel."
        )
        return None

    def _can_send(ch: discord.TextChannel) -> bool:
        try:
            return ch.permissions_for(guild.me).send_messages
        except Exception:
            return False

    seen_ids: set[int] = set()
    candidates: list[discord.TextChannel] = []

    def _add_candidate(ch: typing.Optional[discord.TextChannel]) -> None:
        if ch is not None and isinstance(ch, discord.TextChannel) and ch.id not in seen_ids:
            seen_ids.add(ch.id)
            candidates.append(ch)

    for ch in guild.text_channels:
        if any(keyword in ch.name.lower() for keyword in _ANTI_KEYWORDS):
            _add_candidate(ch)

    for ch in guild.text_channels:
        if any(keyword in ch.name.lower() for keyword in _LOG_KEYWORDS):
            _add_candidate(ch)

    if guild.public_updates_channel:
        _add_candidate(guild.public_updates_channel)

    if guild.system_channel:
        _add_candidate(guild.system_channel)

    for ch in candidates:
        if _can_send(ch):
            return ch

    for ch in guild.text_channels:
        if _can_send(ch):
            return ch

    return None


async def _safe_send(channel: typing.Optional[discord.TextChannel], **kwargs) -> typing.Optional[discord.Message]:
    """
    Gửi tin nhắn an toàn — nuốt mọi lỗi Discord để không crash pipeline log.
    """
    if channel is None:
        logger.warning(
            "[AntiCog][_safe_send] Không tìm được log channel — "
            "log embed bị bỏ qua. Kiểm tra lại tên kênh (cần chứa 'anti' hoặc 'log') "
            "và quyền send_messages của Bot."
        )
        return None
    try:
        return await channel.send(**kwargs)
    except discord.Forbidden:
        logger.warning(
            f"[AntiCog][_safe_send] Bị từ chối quyền gửi tin vào #{channel.name} "
            f"(ID: {channel.id}) tại guild {channel.guild.id}. "
            f"Kiểm tra lại quyền Send Messages của Bot trong kênh này."
        )
        return None
    except discord.HTTPException as e:
        logger.error(
            f"[AntiCog][_safe_send] HTTP lỗi khi gửi log vào #{channel.name} "
            f"(ID: {channel.id}): status={e.status} code={e.code} text={e.text}"
        )
        return None


# ─────────────────────────────────────────────────────────────────────────
# HELPER MỚI: GỬI EMBED CẢNH BÁO TRỰC TIẾP TẠI KÊNH VI PHẠM
# ─────────────────────────────────────────────────────────────────────────
async def _notify_violation_channel(
    channel: discord.TextChannel,
    user: discord.Member,
    violation_type: str,
    action_taken: str
) -> None:
    """
    Gửi một Embed cảnh báo gọn, thân thiện trực tiếp vào kênh vừa xảy ra vi phạm.

    - Không chứa thông tin kỹ thuật nhạy cảm (ID, chi tiết hệ thống).
    - Chỉ mang tính chất cảnh báo người dùng.
    - Bọc trong try...except để không crash pipeline nếu bot thiếu quyền.
    """
    embed = discord.Embed(
        description=(
            f"{_ICO_STOP} {user.mention}, bạn đã vi phạm quy định **{violation_type}**.\n"
            f"> {action_taken}\n"
            f"> *Vui lòng tuân thủ nội quy server để tránh bị xử lý nặng hơn.*"
        ),
        color=_CLR_WARN_CH,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=f"{_BRAND} — Cảnh báo vi phạm")
    embed.set_footer(text="Tin nhắn này là cảnh báo chính thức.")

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        logger.warning(
            f"[AntiCog][_notify_violation_channel] Bot thiếu quyền Send Messages / Embed Links "
            f"tại #{channel.name} ({channel.id}) — bỏ qua channel notification."
        )
    except discord.HTTPException as e:
        logger.warning(
            f"[AntiCog][_notify_violation_channel] HTTP lỗi khi gửi channel notification "
            f"tại #{channel.name}: status={e.status} code={e.code}"
        )


# ─────────────────────────────────────────────────────────────────────────
# HELPER: XÂY DỰNG EMBED TRẠNG THÁI HỆ THỐNG ANTI
# ─────────────────────────────────────────────────────────────────────────
def _build_anti_status_embed(guild: discord.Guild, mode: str) -> discord.Embed:
    """
    Tạo Embed hiển thị trạng thái 3 tính năng Anti theo guild.
    mode: "on"  -> Embed hướng dẫn BẬT tính năng.
    mode: "off" -> Embed hướng dẫn TẮT tính năng.
    """
    al = get_anti_setting(guild.id, "antilink")
    sp = get_anti_setting(guild.id, "antispam")
    nk = get_anti_setting(guild.id, "antinuke")

    is_on  = (mode == "on")
    color  = _CLR_SUCCESS if is_on else _CLR_DANGER
    verb   = "KÍCH HOẠT" if is_on else "VÔ HIỆU HÓA"

    embed = discord.Embed(
        title=f"{_ICO_SHIELD}  {_BRAND} — Bảng Điều Khiển Bảo Vệ",
        description=(
            f"> Chọn module muốn **{verb}** từ menu bên dưới.\n"
            f"> Chỉ **Quản trị viên / Chủ sở hữu** mới có quyền thao tác.\n"
            f"{_DIVIDER}"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name=f"{_ICO_LINK}  ANTI-LINK",
        value=(
            f"> **Trạng thái:** {_status_badge(al)}\n"
            f"> Chặn & xóa liên kết trái phép\n"
            f"> Discord AutoMod API (tầng Gateway)\n"
            f"> phát hiện phân tán từ nhiều nguồn"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{_ICO_CHAT}  ANTI-SPAM",
        value=(
            f"> **Trạng thái:** {_status_badge(sp)}\n"
            f"> Timeout 7h khi gửi <`1.0s`/tin\n"
            f"> Discord AutoMod API chặn tầng API\n"
            f"> Không ảnh hưởng người có `Manage Messages`"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{_ICO_STOP}  ANTI-NUKE",
        value=(
            f"> **Trạng thái:** {_status_badge(nk)}\n"
            f"> Phát hiện xóa kênh / ban hàng loạt\n"
            f"> GlobalRateLimiter + Audit Log\n"
            f"> 2 lớp phòng thủ song song"
        ),
        inline=True
    )

    embed.set_footer(
        text=f"{_BRAND}  ·  {guild.name}  ·  ID: {guild.id}"
    )
    return embed


# ─────────────────────────────────────────────────────────────────────────
# HELPER: TIMEOUT EMBED (dùng chung cho cả AntiOnView & AntiOffView)
# ─────────────────────────────────────────────────────────────────────────
def _build_timeout_embed() -> discord.Embed:
    return discord.Embed(
        title=f"{_ICO_TIME}  Phiên điều khiển đã hết hạn",
        description=(
            f"> Menu tự động vô hiệu hóa sau **120 giây** không hoạt động.\n"
            f"> Gọi lại lệnh để mở bảng điều khiển mới.\n"
            f"{_DIVIDER}\n"
            f"> *{_BRAND} · Security Session Expired*"
        ),
        color=_CLR_TIMEOUT
    )


# ─────────────────────────────────────────────────────────────────────────
# HELPER: EMBED LỖI QUYỀN HẠN (dùng chung)
# ─────────────────────────────────────────────────────────────────────────
def _build_perm_denied_embed() -> discord.Embed:
    return discord.Embed(
        title=f"{_ICO_STOP}  Truy cập bị từ chối",
        description=(
            f"> Bạn **không có quyền** thao tác với bảng điều khiển này.\n"
            f"{_DIVIDER}\n"
            f"> **Yêu cầu:** `Administrator` hoặc `Server Owner`\n"
            f"> *{_BRAND} · Access Control*"
        ),
        color=_CLR_DANGER
    )


# ─────────────────────────────────────────────────────────────────────────
# HELPER: EMBED LỖI LỆNH (thiếu quyền admin khi gọi lệnh)
# ─────────────────────────────────────────────────────────────────────────
def _build_cmd_perm_denied_embed() -> discord.Embed:
    return discord.Embed(
        title=f"{_ICO_STOP}  Không đủ quyền hạn",
        description=(
            f"> Lệnh này chỉ dành cho **Quản trị viên** và **Chủ sở hữu** server.\n"
            f"{_DIVIDER}\n"
            f"> **Yêu cầu:** `Administrator` hoặc `Server Owner`\n"
            f"> *{_BRAND} · Permission Gate*"
        ),
        color=_CLR_DANGER
    )


# ─────────────────────────────────────────────────────────────────────────
# KIỂM TRA QUYỀN ADMIN (dùng chung cho cả slash và prefix)
# ─────────────────────────────────────────────────────────────────────────
def _is_admin(user: discord.Member, guild: discord.Guild) -> bool:
    return user.guild_permissions.administrator or user.id == guild.owner_id


# ─────────────────────────────────────────────────────────────────────────
# HELPER: ĐẾM EMOJI UNICODE + DISCORD CUSTOM EMOJI
# ─────────────────────────────────────────────────────────────────────────
def _count_emoji(content: str) -> int:
    """
    Đếm tổng số emoji trong nội dung tin nhắn.
    Bao gồm: Unicode emoji và Discord custom emoji dạng <:name:id> / <a:name:id>.
    """
    # Discord custom emoji: <:name:id> hoặc <a:name:id>
    custom_emoji_count = len(re.findall(r"<a?:[a-zA-Z0-9_]+:\d+>", content))

    # Unicode emoji — dải phổ biến nhất
    unicode_emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
        "\U0001F680-\U0001F6FF"  # Transport and Map
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002600-\U000026FF"  # Misc symbols
        "\U00002700-\U000027BF"  # Dingbats
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002300-\U000023FF"  # Misc Technical
        "]+",
        flags=re.UNICODE
    )
    unicode_emoji_count = len(unicode_emoji_pattern.findall(content))

    return custom_emoji_count + unicode_emoji_count


# ─────────────────────────────────────────────────────────────────────────
# AUTOMOD HELPERS — TẠO / XÓA RULES QUA DISCORD API
# ─────────────────────────────────────────────────────────────────────────
async def _find_automod_rule(
    guild: discord.Guild,
    rule_name: str
) -> typing.Optional[discord.AutoModRule]:
    """
    Tìm AutoMod rule theo tên trong guild.
    Trả về rule đầu tiên khớp tên, hoặc None nếu không tìm thấy.
    """
    try:
        rules = await guild.fetch_automod_rules()
        for rule in rules:
            if rule.name == rule_name:
                return rule
    except discord.Forbidden:
        logger.warning(
            f"[AutoMod] Bot thiếu quyền `Manage AutoMod` để fetch AutoMod rules "
            f"tại guild {guild.id}. Kiểm tra Server Settings → Integrations."
        )
    except discord.HTTPException as e:
        logger.warning(
            f"[AutoMod] Lỗi HTTP khi fetch AutoMod rules tại guild {guild.id}: "
            f"status={e.status} code={e.code} text={e.text}"
        )
    return None


async def _delete_automod_rule_by_name(
    guild: discord.Guild,
    rule_name: str
) -> bool:
    """
    Xóa AutoMod rule theo tên. Trả về True nếu xóa thành công.

    Xử lý ngoại lệ:
      - discord.NotFound  : rule đã bị xóa từ trước → coi như thành công (không cần xóa nữa).
      - discord.Forbidden : bot thiếu quyền Manage AutoMod → log cảnh báo, trả về False.
      - discord.HTTPException : lỗi HTTP khác → log error, trả về False.
    """
    rule = await _find_automod_rule(guild, rule_name)
    if rule is None:
        logger.debug(
            f"[AutoMod] Không tìm thấy rule '{rule_name}' tại guild {guild.id} "
            f"— có thể đã bị xóa trước đó hoặc chưa từng được tạo."
        )
        return False
    try:
        await rule.delete(reason=f"[{_BRAND}] Module bị vô hiệu hóa bởi Admin")
        logger.info(f"[AutoMod] Đã xóa rule '{rule_name}' (ID: {rule.id}) tại guild {guild.id}.")
        return True
    except discord.NotFound:
        # Rule đã bị xóa thủ công trong khoảng thời gian fetch → xóa rồi, coi là thành công
        logger.info(
            f"[AutoMod] Rule '{rule_name}' tại guild {guild.id} đã bị xóa trước đó (NotFound). "
            f"Bỏ qua — không cần thao tác thêm."
        )
        return True
    except discord.Forbidden:
        logger.warning(
            f"[AutoMod] Bot thiếu quyền `Manage AutoMod` để xóa rule '{rule_name}' "
            f"tại guild {guild.id}. Kiểm tra lại quyền của Bot trong Server Settings → Integrations."
        )
        return False
    except discord.HTTPException as e:
        logger.warning(
            f"[AutoMod] Lỗi HTTP khi xóa rule '{rule_name}' tại guild {guild.id}: "
            f"status={e.status} code={e.code} text={e.text}"
        )
        return False


async def _ensure_antilink_automod_rule(guild: discord.Guild) -> typing.Optional[discord.AutoModRule]:
    """
    Tạo hoặc cập nhật AutoMod rule chặn liên kết (Anti-Link).
    """
    await _delete_automod_rule_by_name(guild, _AUTOMOD_RULE_ANTILINK)

    log_channel = _get_log_channel(guild)

    actions: list[discord.AutoModRuleAction] = [
        discord.AutoModRuleAction(
            type=discord.AutoModRuleActionType.block_message,
            custom_message=(
                f"[{_BRAND}] Liên kết bị chặn — Bạn không có quyền gửi link tại server này."
            )
        )
    ]
    if log_channel is not None:
        actions.append(
            discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.send_alert_message,
                channel_id=log_channel.id
            )
        )

    keyword_filter = [
        "http://*",
        "https://*",
        "discord.gg/*",
        "discord.com/invite/*",
        "discordapp.com/invite/*",
        "*.com/*",
        "*.net/*",
        "*.org/*",
        "*.io/*",
        "*.gg/*",
        "hxxp*",
    ]

    try:
        rule = await guild.create_automod_rule(
            name=_AUTOMOD_RULE_ANTILINK,
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=keyword_filter,
            ),
            actions=actions,
            enabled=True,
            exempt_permissions=[discord.Permissions(manage_messages=True)],
            reason=f"[{_BRAND}] Anti-Link module được kích hoạt bởi Admin"
        )
        logger.info(f"[AutoMod] Đã tạo Anti-Link rule (ID: {rule.id}) tại guild {guild.id}.")
        return rule
    except discord.Forbidden:
        logger.warning(
            f"[AutoMod] Bot thiếu quyền Manage Guild / Manage AutoMod để tạo Anti-Link rule "
            f"tại guild {guild.id}."
        )
        return None
    except discord.HTTPException as e:
        logger.error(
            f"[AutoMod] Lỗi HTTP khi tạo Anti-Link rule tại guild {guild.id}: "
            f"status={e.status} code={e.code} text={e.text}"
        )
        return None


async def _ensure_antispam_automod_rule(guild: discord.Guild) -> typing.Optional[discord.AutoModRule]:
    """
    Tạo hoặc cập nhật AutoMod rule chống spam mention (Anti-Spam).
    """
    await _delete_automod_rule_by_name(guild, _AUTOMOD_RULE_ANTISPAM)

    log_channel = _get_log_channel(guild)

    actions: list[discord.AutoModRuleAction] = [
        discord.AutoModRuleAction(
            type=discord.AutoModRuleActionType.timeout,
            duration=timedelta(hours=7)
        )
    ]
    if log_channel is not None:
        actions.append(
            discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.send_alert_message,
                channel_id=log_channel.id
            )
        )

    try:
        rule = await guild.create_automod_rule(
            name=_AUTOMOD_RULE_ANTISPAM,
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.mention_spam,
                mention_total_limit=5,
            ),
            actions=actions,
            enabled=True,
            exempt_permissions=[discord.Permissions(manage_messages=True)],
            reason=f"[{_BRAND}] Anti-Spam module được kích hoạt bởi Admin"
        )
        logger.info(f"[AutoMod] Đã tạo Anti-Spam rule (ID: {rule.id}) tại guild {guild.id}.")
        return rule
    except discord.Forbidden:
        logger.warning(
            f"[AutoMod] Bot thiếu quyền Manage Guild / Manage AutoMod để tạo Anti-Spam rule "
            f"tại guild {guild.id}."
        )
        return None
    except discord.HTTPException as e:
        logger.error(
            f"[AutoMod] Lỗi HTTP khi tạo Anti-Spam rule tại guild {guild.id}: "
            f"status={e.status} code={e.code} text={e.text}"
        )
        return None


# ─────────────────────────────────────────────────────────────────────────
# SELECT MENU: BẬT ANTI
# ─────────────────────────────────────────────────────────────────────────
class AntiOnSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Anti Link",
                value="antilink",
                description="Bật module chặn & xóa liên kết trái phép",
                emoji="<:link:1522569128760709190>"
            ),
            discord.SelectOption(
                label="Anti Spam",
                value="antispam",
                description="Bật module timeout khi gửi tin < 1.0 giây/tin",
                emoji="<:chat:1521762991677247608>"
            ),
            discord.SelectOption(
                label="Anti Nuke",
                value="antinuke",
                description="Bật module chống phá hoại server 2 lớp bảo vệ",
                emoji="<:stop:1521777358485327872>"
            ),
            discord.SelectOption(
                label="Kích hoạt tất cả (All Anti)",
                value="all",
                description="Bật đồng thời cả 3 module Anti cùng lúc",
                emoji="<:khien:1522083687645319278>"
            ),
        ]
        super().__init__(
            placeholder="Chọn module để kích hoạt...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="anti_on_select"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=_build_perm_denied_embed(),
                ephemeral=True
            )
            return

        chosen = self.values[0]
        guild  = interaction.guild

        await interaction.response.defer(ephemeral=False)

        automod_status_lines: list[str] = []

        if chosen in ("all", "antilink"):
            update_anti_db(guild.id, "antilink", 1)
            rule = await _ensure_antilink_automod_rule(guild)
            if rule:
                automod_status_lines.append(f"> {_ICO_TICK} **Anti-Link AutoMod Rule** đã tạo (ID: `{rule.id}`)")
            else:
                automod_status_lines.append(f"> {_ICO_STOP} **Anti-Link AutoMod Rule** — Bot thiếu quyền `Manage AutoMod`")

        if chosen in ("all", "antispam"):
            update_anti_db(guild.id, "antispam", 1)
            rule = await _ensure_antispam_automod_rule(guild)
            if rule:
                automod_status_lines.append(f"> {_ICO_TICK} **Anti-Spam AutoMod Rule** đã tạo (ID: `{rule.id}`)")
            else:
                automod_status_lines.append(f"> {_ICO_STOP} **Anti-Spam AutoMod Rule** — Bot thiếu quyền `Manage AutoMod`")

        if chosen in ("all", "antinuke"):
            update_anti_db(guild.id, "antinuke", 1)
            automod_status_lines.append(f"> {_ICO_TICK} **Anti-Nuke** đã kích hoạt (GlobalRateLimiter + Audit Log)")

        if chosen == "all":
            result_title   = "Kích hoạt toàn bộ hệ thống"
            result_modules = "`Anti-Link`  +  `Anti-Spam`  +  `Anti-Nuke`"
        elif chosen == "antilink":
            result_title   = "Module đã kích hoạt"
            result_modules = "`Anti-Link`"
        elif chosen == "antispam":
            result_title   = "Module đã kích hoạt"
            result_modules = "`Anti-Spam`"
        else:
            result_title   = "Module đã kích hoạt"
            result_modules = "`Anti-Nuke`"

        updated_embed = _build_anti_status_embed(guild, mode="on")
        updated_embed.add_field(
            name=f"{_ICO_RESULT}  {result_title}",
            value=(
                f"{_DIVIDER}\n"
                f"> {_ICO_TICK} **Trạng thái:** ACTIVE\n"
                f"> **Module:** {result_modules}\n"
                f"> **Thực hiện bởi:** {interaction.user.mention}\n"
                f"{_DIVIDER}"
            ),
            inline=False
        )
        if automod_status_lines:
            updated_embed.add_field(
                name=f"{_ICO_SHIELD}  Discord AutoMod API",
                value="\n".join(automod_status_lines),
                inline=False
            )

        try:
            await interaction.edit_original_response(embed=updated_embed, view=self.view)
        except (discord.NotFound, discord.HTTPException):
            pass


class AntiOnView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AntiOnSelect())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if not hasattr(self, "message") or self.message is None:
            return
        try:
            await self.message.edit(
                embed=_build_timeout_embed(),
                view=self
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


# ─────────────────────────────────────────────────────────────────────────
# SELECT MENU: TẮT ANTI
# ─────────────────────────────────────────────────────────────────────────
class AntiOffSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Anti Link",
                value="antilink",
                description="Tắt module chặn liên kết trái phép",
                emoji="<:link:1522569128760709190>"
            ),
            discord.SelectOption(
                label="Anti Spam",
                value="antispam",
                description="Tắt module kiểm soát tốc độ gửi tin nhắn",
                emoji="<:chat:1521762991677247608>"
            ),
            discord.SelectOption(
                label="Anti Nuke",
                value="antinuke",
                description="Tắt module chống phá hoại server",
                emoji="<:stop:1521777358485327872>"
            ),
            discord.SelectOption(
                label="Vô hiệu hóa tất cả (Disable All)",
                value="all",
                description="Tắt đồng thời cả 3 module Anti cùng lúc",
                emoji="<a:khoa:1522079387820752977>"
            ),
        ]
        super().__init__(
            placeholder="Chọn module để vô hiệu hóa...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="anti_off_select"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=_build_perm_denied_embed(),
                ephemeral=True
            )
            return

        chosen = self.values[0]
        guild  = interaction.guild

        await interaction.response.defer(ephemeral=False)

        automod_status_lines: list[str] = []

        if chosen in ("all", "antilink"):
            update_anti_db(guild.id, "antilink", 0)
            deleted = await _delete_automod_rule_by_name(guild, _AUTOMOD_RULE_ANTILINK)
            if deleted:
                automod_status_lines.append(f"> {_ICO_TICK} **Anti-Link AutoMod Rule** đã xóa khỏi Discord")
            else:
                automod_status_lines.append(f"> {_ICO_RESULT} **Anti-Link AutoMod Rule** — Không tìm thấy hoặc đã xóa từ trước")

        if chosen in ("all", "antispam"):
            update_anti_db(guild.id, "antispam", 0)
            deleted = await _delete_automod_rule_by_name(guild, _AUTOMOD_RULE_ANTISPAM)
            if deleted:
                automod_status_lines.append(f"> {_ICO_TICK} **Anti-Spam AutoMod Rule** đã xóa khỏi Discord")
            else:
                automod_status_lines.append(f"> {_ICO_RESULT} **Anti-Spam AutoMod Rule** — Không tìm thấy hoặc đã xóa từ trước")

        if chosen in ("all", "antinuke"):
            update_anti_db(guild.id, "antinuke", 0)
            automod_status_lines.append(f"> {_ICO_LOCK} **Anti-Nuke** đã vô hiệu hóa (GlobalRateLimiter tạm dừng)")

        if chosen == "all":
            result_title   = "Vô hiệu hóa toàn bộ hệ thống"
            result_modules = "`Anti-Link`  +  `Anti-Spam`  +  `Anti-Nuke`"
        elif chosen == "antilink":
            result_title   = "Module đã vô hiệu hóa"
            result_modules = "`Anti-Link`"
        elif chosen == "antispam":
            result_title   = "Module đã vô hiệu hóa"
            result_modules = "`Anti-Spam`"
        else:
            result_title   = "Module đã vô hiệu hóa"
            result_modules = "`Anti-Nuke`"

        updated_embed = _build_anti_status_embed(guild, mode="off")
        updated_embed.add_field(
            name=f"{_ICO_RESULT}  {result_title}",
            value=(
                f"{_DIVIDER}\n"
                f"> {_ICO_LOCK} **Trạng thái:** OFFLINE\n"
                f"> **Module:** {result_modules}\n"
                f"> **Thực hiện bởi:** {interaction.user.mention}\n"
                f"{_DIVIDER}"
            ),
            inline=False
        )
        if automod_status_lines:
            updated_embed.add_field(
                name=f"{_ICO_SHIELD}  Discord AutoMod API",
                value="\n".join(automod_status_lines),
                inline=False
            )

        try:
            await interaction.edit_original_response(embed=updated_embed, view=self.view)
        except (discord.NotFound, discord.HTTPException):
            pass


class AntiOffView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AntiOffSelect())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if not hasattr(self, "message") or self.message is None:
            return
        try:
            await self.message.edit(
                embed=_build_timeout_embed(),
                view=self
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


# =========================================================================
# COG CHÍNH — SAFE-ANTI 2.0
# =========================================================================
class AntiCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Lưu trữ timestamps của tin nhắn phục vụ fallback Anti Spam on_message
        self.user_last_msg_times: dict = {}

        # Cờ trạng thái: True khi server đang trong chế độ Lockdown.
        self.under_attack: bool = False

        # Bộ đếm link-spam phân tán theo từng kênh (fallback khi AutoMod rule chưa có).
        # channel_id -> deque các timestamp (time.monotonic()) của tin nhắn
        self._link_spam_events: defaultdict = defaultdict(deque)
        self.LINK_SPAM_THRESHOLD: int = 5
        self.LINK_SPAM_WINDOW: float = 3.0

        # asyncio.Lock bảo vệ under_attack flag khỏi race condition.
        self._lockdown_lock: asyncio.Lock = asyncio.Lock()

        # asyncio.Lock bảo vệ _link_spam_events khỏi race condition
        self._link_spam_lock: asyncio.Lock = asyncio.Lock()

        # asyncio.Lock bảo vệ user_last_msg_times khỏi race condition
        self._spam_times_lock: asyncio.Lock = asyncio.Lock()

        # Bot-raid detection: tracks timestamps of bot joins per guild.
        self._bot_join_events: defaultdict = defaultdict(deque)
        self.BOT_RAID_THRESHOLD: int = 3
        self.BOT_RAID_WINDOW: float = 10.0
        self._bot_raid_lock: asyncio.Lock = asyncio.Lock()

        # [SAFE-ANTI 2.0] Anti-Channel Rename: lưu tên/topic cũ của kênh
        # key: channel_id → {"name": str, "topic": str | None}
        # Được populate trong on_ready và on_guild_channel_create.
        self._channel_info_cache: dict[int, dict] = {}
        self._channel_cache_lock: asyncio.Lock = asyncio.Lock()

        # Task dọn dẹp định kỳ
        self._cleanup_task: typing.Optional[asyncio.Task] = None

    # =========================================================================
    # COG LIFECYCLE — KHỞI ĐỘNG VÀ DỪNG BACKGROUND TASK
    # =========================================================================
    async def cog_load(self) -> None:
        self._cleanup_task = asyncio.create_task(self._memory_cleanup_loop())
        logger.info("[AntiCog] Background cleanup task đã khởi động.")

    async def cog_unload(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("[AntiCog] Background cleanup task đã dừng.")

    # =========================================================================
    # KHỞI TẠO CACHE TÊN KÊNH KHI BOT SẴN SÀNG
    # =========================================================================
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        [SAFE-ANTI 2.0] Khi bot ready, snapshot toàn bộ thông tin kênh
        của tất cả guild để phục vụ Anti-Channel Rename.
        """
        async with self._channel_cache_lock:
            for guild in self.bot.guilds:
                for ch in guild.channels:
                    if isinstance(ch, (discord.TextChannel, discord.VoiceChannel,
                                       discord.StageChannel, discord.ForumChannel)):
                        topic = getattr(ch, "topic", None)
                        self._channel_info_cache[ch.id] = {
                            "name": ch.name,
                            "topic": topic
                        }
        logger.info(
            f"[AntiCog][ChannelCache] Đã snapshot {len(self._channel_info_cache)} kênh "
            f"từ {len(self.bot.guilds)} guild."
        )

    # =========================================================================
    # BACKGROUND TASK DỌN DẸP BỘ NHỚ
    # =========================================================================
    async def _memory_cleanup_loop(self) -> None:
        """
        Task chạy vô hạn, mỗi 5 phút thức dậy một lần để:
        1. Xóa timestamp cũ khỏi _link_spam_events + xóa key channel_id rỗng.
        2. Xóa entry trong user_last_msg_times cho user không hoạt động > 10 phút.
        3. Dọn _bot_join_events cũ.
        4. Dọn _channel_info_cache cho kênh không còn tồn tại.

        Ngăn chặn tích lũy key rác theo thời gian chạy lâu dài.
        Luôn acquire lock tương ứng để tránh race condition.
        """
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(300)

                now_mono = time.monotonic()
                cutoff_link = now_mono - self.LINK_SPAM_WINDOW
                keys_link_cleaned = 0

                async with self._link_spam_lock:
                    stale_keys = [
                        ch_id for ch_id, dq in self._link_spam_events.items()
                        if not dq or dq[-1] <= cutoff_link
                    ]
                    for ch_id in stale_keys:
                        dq = self._link_spam_events[ch_id]
                        while dq and dq[0] <= cutoff_link:
                            dq.popleft()
                        if not dq:
                            del self._link_spam_events[ch_id]
                            keys_link_cleaned += 1

                if keys_link_cleaned > 0:
                    logger.debug(
                        f"[AntiLink][Cleanup] Đã dọn {keys_link_cleaned} key channel_id cũ. "
                        f"Còn lại: {len(self._link_spam_events)} key."
                    )

                # Dọn user_last_msg_times — giữ lại user hoạt động trong 10 phút gần nhất
                now_utc = datetime.now(timezone.utc)
                spam_cutoff = now_utc - timedelta(minutes=10)
                keys_spam_cleaned = 0

                async with self._spam_times_lock:
                    stale_users = [
                        uid for uid, ts in self.user_last_msg_times.items()
                        if ts < spam_cutoff
                    ]
                    for uid in stale_users:
                        del self.user_last_msg_times[uid]
                        keys_spam_cleaned += 1

                if keys_spam_cleaned > 0:
                    logger.debug(
                        f"[AntiSpam][Cleanup] Đã dọn {keys_spam_cleaned} user timestamp cũ. "
                        f"Còn lại: {len(self.user_last_msg_times)} entry."
                    )

                # Dọn _bot_join_events
                bot_cutoff = now_mono - self.BOT_RAID_WINDOW
                async with self._bot_raid_lock:
                    stale_guilds = [
                        gid for gid, dq in self._bot_join_events.items()
                        if not dq or dq[-1] <= bot_cutoff
                    ]
                    for gid in stale_guilds:
                        del self._bot_join_events[gid]

                # Dọn _channel_info_cache — xóa kênh không còn trong bất kỳ guild nào
                all_channel_ids: set[int] = set()
                for guild in self.bot.guilds:
                    for ch in guild.channels:
                        all_channel_ids.add(ch.id)

                async with self._channel_cache_lock:
                    stale_channels = [
                        ch_id for ch_id in list(self._channel_info_cache.keys())
                        if ch_id not in all_channel_ids
                    ]
                    for ch_id in stale_channels:
                        del self._channel_info_cache[ch_id]

                if stale_channels:
                    logger.debug(
                        f"[AntiRename][Cleanup] Đã dọn {len(stale_channels)} kênh đã xóa "
                        f"khỏi channel cache. Còn lại: {len(self._channel_info_cache)} entry."
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AntiCog][Cleanup] Lỗi không mong đợi trong cleanup loop: {e}")

    # =========================================================================
    # MULTI-STAGE SECURITY LOGGING — HÀM TIỆN ÍCH
    # =========================================================================
    async def _log_phase1_detection(
        self,
        guild: discord.Guild,
        event_type: str,
        event_count: int,
        window_seconds: float,
        source: str = "GlobalRateLimiter"
    ) -> typing.Optional[discord.Message]:
        """
        Giai đoạn 1: Gửi embed BÁO ĐỘNG ngay khi phát hiện dấu hiệu tấn công.
        """
        ch = _get_log_channel(guild)
        if ch is None:
            return None

        embed = discord.Embed(
            title=f"{_ICO_STOP} CẢNH BÁO — ĐANG PHÁT HIỆN DẤU HIỆU TẤN CÔNG",
            description=(
                f"> {_ICO_SHIELD} Hệ thống **{_BRAND}** vừa ghi nhận hoạt động bất thường.\n"
                f"> Đang phân tích và chuẩn bị phản ứng...\n"
                f"{_DIVIDER}"
            ),
            color=_CLR_PHASE1,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name=f"{_ICO_RESULT} Chi tiết phát hiện",
            value=(
                f"> **Loại sự kiện:** `{event_type}`\n"
                f"> **Tần suất:** `{event_count}` sự kiện trong `{window_seconds}s`\n"
                f"> **Nguồn phát hiện:** `{source}`\n"
                f"> **Thời điểm:** <t:{int(datetime.now(timezone.utc).timestamp())}:T>"
            ),
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_STOP} Trạng thái",
            value=f"> {_ICO_TIME} **Đang đánh giá mức độ nguy hiểm...**",
            inline=False
        )
        embed.set_footer(text=f"{_BRAND} · Phase 1: Detection · Guild: {guild.id}")

        return await _safe_send(ch, embed=embed)

    async def _log_phase2_progress(
        self,
        guild: discord.Guild,
        step_message: str
    ) -> None:
        """
        Giai đoạn 2: Gửi cập nhật trạng thái ngắn gọn trong quá trình xử lý lockdown.
        """
        ch = _get_log_channel(guild)
        if ch is None:
            return

        embed = discord.Embed(
            description=f"> {_ICO_LOCK} **[LOCKDOWN ĐANG CHẠY]** {step_message}",
            color=_CLR_PHASE2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"{_BRAND} · Phase 2: Processing · Guild: {guild.id}")
        await _safe_send(ch, embed=embed)

    async def _log_phase3_complete(
        self,
        guild: discord.Guild,
        reason: str,
        roles_stripped: list[str],
        roles_skipped: list[str],
        hierarchy_bypass: bool = False,
        bypass_user: typing.Optional[discord.Member] = None
    ) -> None:
        """
        Giai đoạn 3: Gửi embed tổng kết ĐÁNH CHẶN THÀNH CÔNG.
        """
        ch = _get_log_channel(guild)
        if ch is None:
            return

        stripped_summary = (
            "\n".join(f"> {_ICO_TICK} `{r}`" for r in roles_stripped)
            if roles_stripped else f"> `Không có role nào bị ảnh hưởng`"
        )
        skipped_summary = (
            ", ".join(f"`{r}`" for r in roles_skipped[:5])
            + ("..." if len(roles_skipped) > 5 else "")
            if roles_skipped else "`Không có`"
        )

        title = (
            f"{_ICO_STOP}  ĐÁNH CHẶN THÀNH CÔNG — BYPASS HIERARCHY ĐƯỢC XỬ LÝ"
            if hierarchy_bypass else
            f"{_ICO_TICK}  ĐÁNH CHẶN THÀNH CÔNG — SERVER ĐÃ ĐƯỢC BẢO VỆ"
        )

        embed = discord.Embed(
            title=title,
            description=(
                f"> Hệ thống **{_BRAND}** đã hoàn tất phản ứng khẩn cấp.\n"
                f"> Server đang ở **chế độ bảo vệ tối đa**.\n"
                f"{_DIVIDER}"
            ),
            color=_CLR_BYPASS if hierarchy_bypass else _CLR_SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name=f"{_ICO_RESULT} Lý do kích hoạt",
            value=f"> {reason}",
            inline=False
        )

        if hierarchy_bypass and bypass_user:
            embed.add_field(
                name=f"{_ICO_STOP} Cảnh báo Bypass Hierarchy",
                value=(
                    f"> **Thủ phạm:** {bypass_user.mention} (`{bypass_user}`)\n"
                    f"> **Top Role:** `{bypass_user.top_role.name}` (cao hơn hoặc bằng Bot)\n"
                    f"> **Trạng thái:** Bot **KHÔNG THỂ** kick/ban trực tiếp\n"
                    f"> → Đã chuyển sang cô lập toàn bộ quyền hạn bên dưới"
                ),
                inline=False
            )

        embed.add_field(
            name=f"{_ICO_SHIELD}  Role đã bị tước quyền nguy hiểm ({len(roles_stripped)} role)",
            value=stripped_summary[:1000] if stripped_summary else "> `Không có`",
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_RESULT}  Role bị bỏ qua (cao hơn Bot / managed)",
            value=f"> {skipped_summary}",
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_LOCK}  Mức độ an toàn hiện tại",
            value=(
                f"> {_ICO_TICK} Verification Level → **`HIGHEST`**\n"
                f"> {_ICO_TICK} Quyền nguy hiểm của `{len(roles_stripped)}` role đã bị vô hiệu\n"
                f"> {_ICO_STOP} Server đang trong **chế độ bảo vệ khẩn cấp**"
            ),
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_TICK} Hướng dẫn khôi phục",
            value=(
                f"> **Bước 1:** Kiểm tra `Audit Log` để xác định và ban thủ phạm.\n"
                f"> **Bước 2:** Khôi phục quyền các role cần thiết thủ công.\n"
                f"> **Bước 3:** Hạ Verification Level về mức phù hợp.\n"
                f"> **Bước 4:** Thông báo cho thành viên server sau khi ổn định."
            ),
            inline=False
        )
        embed.set_footer(text=f"{_BRAND} · Phase 3: Complete · Guild: {guild.id}")

        await _safe_send(ch, embed=embed)

    # =========================================================================
    # CẢNH BÁO KHẨN CẤP TAG OWNER KHI BYPASS HIERARCHY
    # =========================================================================
    async def _alert_owner_hierarchy_bypass(
        self,
        guild: discord.Guild,
        attacker: discord.Member,
        event_description: str
    ) -> None:
        """
        Gửi cảnh báo khẩn cấp tag trực tiếp Owner khi phát hiện kẻ tấn công
        có role cao hơn hoặc bằng Bot — tình huống Bot không thể kick/ban.
        """
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except (discord.NotFound, discord.HTTPException):
                owner = None

        owner_mention = owner.mention if owner else f"<@{guild.owner_id}>"

        embed = discord.Embed(
            title=f"{_ICO_STOP}  KHẨN CẤP — KẺ TẤN CÔNG CÓ ROLE CAO HƠN BOT",
            description=(
                f"> {owner_mention} **Cần hành động ngay lập tức!**\n"
                f"> Bot **KHÔNG THỂ** kick/ban kẻ tấn công do giới hạn phân cấp Discord.\n"
                f"{_DIVIDER}"
            ),
            color=_CLR_BYPASS,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name=f"{_ICO_RESULT} Thông tin kẻ tấn công",
            value=(
                f"> **Tài khoản:** {attacker.mention} (`{attacker}`)\n"
                f"> **ID:** `{attacker.id}`\n"
                f"> **Top Role:** `{attacker.top_role.name}` (Position: `{attacker.top_role.position}`)\n"
                f"> **Bot Top Role:** `{guild.me.top_role.name}` (Position: `{guild.me.top_role.position}`)"
            ),
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_STOP}  Hành vi phát hiện",
            value=f"> {event_description}",
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_STOP}  Hành động tự động",
            value=(
                f"> {_ICO_LOCK} Đang kích hoạt **LOCKDOWN MỨC CAO NHẤT**\n"
                f"> Tước quyền tất cả role bên dưới để cô lập thiệt hại\n"
                f"> Nâng Verification Level lên **HIGHEST**"
            ),
            inline=False
        )
        embed.add_field(
            name=f"{_ICO_STOP}  Yêu cầu hành động thủ công",
            value=(
                f"> **→ Ban thủ công:** `chuột phải → Ban` vào {attacker.mention}\n"
                f"> **→ Hoặc dùng lệnh:** `/ban {attacker.id}`\n"
                f"> Sau đó khôi phục lại quyền các role và hạ Verification Level."
            ),
            inline=False
        )
        embed.set_footer(text=f"{_BRAND} · HIERARCHY BYPASS ALERT · Guild: {guild.id}")

        ch = _get_log_channel(guild)
        sent_to_channel = False

        if ch:
            msg = await _safe_send(ch, content=owner_mention, embed=embed)
            if msg:
                sent_to_channel = True

        if not sent_to_channel and owner:
            try:
                await owner.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    f"[AntiNuke][Bypass] Không thể DM Owner {guild.owner_id} "
                    f"tại guild {guild.id} — bypass alert bị mất."
                )

        logger.critical(
            f"[AntiNuke][BYPASS] Kẻ tấn công {attacker} (role: {attacker.top_role.name}) "
            f"có phân cấp CAO HƠN Bot tại guild '{guild.name}' ({guild.id}). "
            f"Sự kiện: {event_description}"
        )

    # =========================================================================
    # DENY USE APPLICATION COMMANDS ACROSS ALL CHANNELS
    # =========================================================================
    async def _deny_application_commands(self, guild: discord.Guild, reason: str) -> None:
        """
        Deny 'use_application_commands' permission for @everyone on every text channel.
        Uses Semaphore(5) để tránh rate-limit.
        """
        everyone_role = guild.default_role
        sem = asyncio.Semaphore(5)

        async def _deny_channel(channel: discord.TextChannel) -> None:
            async with sem:
                try:
                    overwrite = channel.overwrites_for(everyone_role)
                    overwrite.use_application_commands = False
                    await channel.set_permissions(
                        everyone_role,
                        overwrite=overwrite,
                        reason=f"[{_BRAND}] {reason} — Slash command lockdown"
                    )
                except discord.Forbidden:
                    logger.warning(
                        f"[AntiNuke][AppCmdLock] Thiếu quyền set_permissions tại "
                        f"#{channel.name} ({channel.id}) guild {guild.id}."
                    )
                except discord.HTTPException as e:
                    logger.error(
                        f"[AntiNuke][AppCmdLock] HTTP lỗi tại #{channel.name}: "
                        f"status={e.status} code={e.code}"
                    )

        text_channels = [
            ch for ch in guild.channels
            if isinstance(ch, discord.TextChannel)
        ]
        await asyncio.gather(*(_deny_channel(ch) for ch in text_channels))
        logger.info(
            f"[AntiNuke][AppCmdLock] Đã deny use_application_commands trên "
            f"{len(text_channels)} kênh tại guild {guild.id}."
        )

    # =========================================================================
    # LOCKDOWN: KHÓA TOÀN BỘ SERVER NGAY LẬP TỨC
    # =========================================================================
    async def _trigger_lockdown(
        self,
        guild: discord.Guild,
        reason: str,
        hierarchy_bypass: bool = False,
        bypass_attacker: typing.Optional[discord.Member] = None
    ) -> None:
        """
        Kích hoạt chế độ Quarantine/Lockdown toàn server khi phát hiện tấn công.

        Thứ tự thực hiện:
        1. Bật cờ self.under_attack (double-checked locking).
        2. Log Giai đoạn 2 theo từng bước.
        3. Tước quyền nguy hiểm khỏi TẤT CẢ role (Semaphore(5) tránh rate-limit).
        4. Nâng verification_level lên highest.
        5. Deny use_application_commands trên tất cả kênh.
        6. Log Giai đoạn 3 tổng kết.
        7. Reset rate limiter.
        8. Reset self.under_attack = False sau cooldown.
        """
        if self.under_attack:
            return

        async with self._lockdown_lock:
            if self.under_attack:
                return
            self.under_attack = True

        logger.warning(
            f"[AntiNuke] LOCKDOWN kích hoạt tại guild '{guild.name}' ({guild.id}) | Lý do: {reason}"
        )

        DANGEROUS_PERMS = {
            "administrator",
            "manage_channels",
            "manage_roles",
            "manage_guild",
            "ban_members",
            "kick_members",
        }

        roles_stripped: list[str] = []
        roles_skipped: list[str] = []

        await self._log_phase2_progress(
            guild,
            f"Đang quét {len(guild.roles)} role để tước quyền nguy hiểm..."
        )

        _role_semaphore = asyncio.Semaphore(5)

        async def _strip_role(role: discord.Role) -> None:
            if role.id == guild.id or role.managed or role >= guild.me.top_role:
                roles_skipped.append(role.name)
                return

            current_perms = role.permissions
            needs_update = any(
                getattr(current_perms, perm, False) for perm in DANGEROUS_PERMS
            )

            if not needs_update:
                return

            new_perms = discord.Permissions(current_perms.value)
            for perm in DANGEROUS_PERMS:
                setattr(new_perms, perm, False)

            async with _role_semaphore:
                try:
                    await role.edit(
                        permissions=new_perms,
                        reason=f"[AntiNuke Lockdown] {reason}"
                    )
                    roles_stripped.append(role.name)
                    logger.info(
                        f"[AntiNuke] Đã tước quyền nguy hiểm khỏi role '{role.name}' tại guild {guild.id}."
                    )
                except discord.Forbidden:
                    roles_skipped.append(role.name)
                    logger.warning(
                        f"[AntiNuke] Không thể chỉnh role '{role.name}' tại guild {guild.id} — "
                        f"thiếu quyền hoặc cấp bậc role cao hơn Bot."
                    )
                except discord.HTTPException as e:
                    roles_skipped.append(role.name)
                    logger.error(
                        f"[AntiNuke] Lỗi HTTP khi chỉnh role '{role.name}' tại guild {guild.id}: "
                        f"status={e.status} code={e.code} text={e.text}"
                    )

        await asyncio.gather(*(_strip_role(role) for role in guild.roles))

        await self._log_phase2_progress(
            guild,
            f"Đã tước quyền `{len(roles_stripped)}` role. "
            f"Đang nâng mức xác minh server lên **HIGHEST**..."
        )

        try:
            await guild.edit(
                verification_level=discord.VerificationLevel.highest,
                reason=f"[AntiNuke Lockdown] {reason}"
            )
            logger.info(f"[AntiNuke] Đã nâng verification_level lên HIGHEST tại guild {guild.id}.")
        except discord.Forbidden:
            logger.warning(
                f"[AntiNuke] Không thể đổi verification_level tại guild {guild.id} — "
                f"Bot thiếu quyền Manage Guild."
            )
        except discord.HTTPException as e:
            logger.error(
                f"[AntiNuke] Lỗi HTTP khi đổi verification_level tại guild {guild.id}: "
                f"status={e.status} code={e.code} text={e.text}"
            )

        await self._log_phase2_progress(
            guild,
            "Verification Level đã được nâng lên **HIGHEST**. "
            "Đang khóa Application Commands trên tất cả kênh..."
        )

        await self._deny_application_commands(
            guild,
            reason=f"AntiNuke Lockdown — {reason}"
        )

        await self._log_phase2_progress(
            guild,
            "Đã deny `use_application_commands` trên toàn server. Đang tổng hợp báo cáo..."
        )

        await self._log_phase3_complete(
            guild=guild,
            reason=reason,
            roles_stripped=roles_stripped,
            roles_skipped=roles_skipped,
            hierarchy_bypass=hierarchy_bypass,
            bypass_user=bypass_attacker
        )

        await server_anti_nuke_limiter.reset(guild.id)

        cooldown_window = getattr(server_anti_nuke_limiter, "window", 10.0)
        await asyncio.sleep(cooldown_window)
        self.under_attack = False

        logger.info(
            f"[AntiNuke] Lockdown hoàn tất tại guild {guild.id}. under_attack reset to False. "
            f"Roles bị tước: {roles_stripped}. Roles bỏ qua: {roles_skipped}."
        )

    # =========================================================================
    # SỰ KIỆN ON_AUTOMOD_ACTION_EXECUTION — LOG VI PHẠM AUTOMOD
    # =========================================================================
    @commands.Cog.listener()
    async def on_automod_action_execution(self, execution: discord.AutoModAction) -> None:
        """
        Nhận callback từ Discord khi AutoMod thực thi một hành động.
        Gửi log bảo mật đa giai đoạn về channel nhật ký của server.
        Chỉ xử lý các rule do SAFE-ANTI 2.0 tạo ra.
        """
        guild = execution.guild
        if guild is None:
            return

        rule_name = execution.rule_name if execution.rule_name else ""
        is_antilink_rule = rule_name == _AUTOMOD_RULE_ANTILINK
        is_antispam_rule = rule_name == _AUTOMOD_RULE_ANTISPAM

        if not is_antilink_rule and not is_antispam_rule:
            return

        ch = _get_log_channel(guild)

        member: typing.Optional[discord.Member] = None
        try:
            member = guild.get_member(execution.user_id) or await guild.fetch_member(execution.user_id)
        except (discord.NotFound, discord.HTTPException):
            pass

        member_display = member.mention if member else f"<@{execution.user_id}>"
        member_tag = str(member) if member else f"ID: {execution.user_id}"

        if is_antilink_rule:
            module_name   = "ANTI-LINK AutoMod"
            module_icon   = _ICO_LINK
            embed_color   = _CLR_PURGE
            action_detail = "Gửi liên kết trái phép — bị chặn tại tầng Discord API"
            content_preview = (
                f"> **Nội dung vi phạm:**\n"
                f"> ```{execution.content[:200] if execution.content else 'N/A'}```"
                if execution.content else ""
            )
            # ── Channel Notification ─────────────────────────────────────
            if member and execution.channel_id:
                event_channel = guild.get_channel(execution.channel_id)
                if isinstance(event_channel, discord.TextChannel):
                    await _notify_violation_channel(
                        channel=event_channel,
                        user=member,
                        violation_type="Anti-Link",
                        action_taken="Tin nhắn chứa liên kết đã bị **chặn tự động**."
                    )
        else:
            module_name   = "ANTI-SPAM AutoMod"
            module_icon   = _ICO_CHAT
            embed_color   = _CLR_DANGER
            action_detail = "Mention quá ngưỡng cho phép — Timeout 7 giờ tự động tại tầng Discord API"
            content_preview = (
                f"> **Nội dung vi phạm:**\n"
                f"> ```{execution.content[:200] if execution.content else 'N/A'}```"
                if execution.content else ""
            )
            # ── Channel Notification ─────────────────────────────────────
            if member and execution.channel_id:
                event_channel = guild.get_channel(execution.channel_id)
                if isinstance(event_channel, discord.TextChannel):
                    await _notify_violation_channel(
                        channel=event_channel,
                        user=member,
                        violation_type="Anti-Spam",
                        action_taken="Bạn đã bị **Timeout 7 giờ** do gửi tin nhắn spam."
                    )

        action_type_display = {
            discord.AutoModRuleActionType.block_message: "Chặn tin nhắn",
            discord.AutoModRuleActionType.send_alert_message: "Gửi cảnh báo",
            discord.AutoModRuleActionType.timeout: "Timeout thành viên",
            discord.AutoModRuleActionType.block_member_interactions: "Chặn tương tác",
        }.get(execution.action.type, f"Loại hành động: {execution.action.type}")

        channel_display = (
            f"<#{execution.channel_id}>" if execution.channel_id else "`(DM / Không rõ)`"
        )

        embed = discord.Embed(
            title=f"{module_icon}  {_BRAND} — {module_name} Vi Phạm Bị Chặn",
            description=(
                f"> Hệ thống **AutoMod Discord** đã tự động chặn vi phạm tại tầng API.\n"
                f"> Không cần xử lý thêm — ghi nhận để Admin theo dõi.\n"
                f"{_DIVIDER}"
            ),
            color=embed_color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name=f"{_ICO_RESULT} Thông tin vi phạm",
            value=(
                f"> **Đối tượng:** {member_display} (`{member_tag}`)\n"
                f"> **Kênh:** {channel_display}\n"
                f"> **Hành vi:** {action_detail}\n"
                f"> **Hành động AutoMod:** `{action_type_display}`\n"
                f"> **Rule ID:** `{execution.rule_id}`"
            ),
            inline=False
        )
        if content_preview:
            embed.add_field(
                name=f"{_ICO_STOP} Nội dung vi phạm (200 ký tự đầu)",
                value=content_preview,
                inline=False
            )
        embed.add_field(
            name=f"{_ICO_SHIELD} Trạng thái xử lý",
            value=(
                f"> {_ICO_TICK} Tin nhắn / hành động đã bị **CHẶN TỰ ĐỘNG** bởi Discord AutoMod\n"
                f"> {_ICO_LOCK} Tầng bảo vệ: **Discord API** (không phụ thuộc gateway)\n"
                f"> *{_BRAND} · AutoMod Security Log*"
            ),
            inline=False
        )
        embed.set_footer(
            text=f"{_BRAND} · AutoMod Action Log · Guild: {guild.id}"
        )

        await _safe_send(ch, embed=embed)

    # =========================================================================
    # SỰ KIỆN ON_MESSAGE: FALLBACK + SAFE-ANTI 2.0 (MASS MENTION & EMOJI SPAM)
    # =========================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Fallback handler cho Anti-Spam và Anti-Link khi AutoMod rule chưa được tạo.

        [SAFE-ANTI 2.0] Thêm hai bộ lọc mới chạy song song:
          - Anti-Mass Mention: > 3 user/role mention → Xóa + Timeout 30 phút
          - Anti-Emoji/Sticker Spam: > 10 emoji/sticker → Xóa + Timeout 15 phút

        [GATE DB] Mỗi module PHẢI kiểm tra cờ tương ứng trong database trước khi
        thực hiện bất kỳ hành động nào (xóa tin, timeout). Nếu status = 0 (đã tắt),
        khối đó phải bỏ qua hoàn toàn — không được xử lý dù điều kiện khác thỏa mãn.

        Lưu ý thứ tự kiểm tra: Mass Mention → Emoji Spam → AntiSpam → AntiLink → Game
        Mỗi vi phạm return sớm, không rơi xuống xử lý game.
        """
        if message.author.bot or not message.guild:
            return

        guild  = message.guild
        author = message.author

        is_protected_author = (
            author.id == guild.owner_id
            or author.id == self.bot.user.id
        )

        if not is_protected_author:
            member_perms  = author.guild_permissions
            is_privileged = (
                member_perms.manage_messages
                or member_perms.manage_roles
                or member_perms.administrator
            )
            can_be_actioned = (
                not is_privileged
                and guild.me is not None
                and author.top_role < guild.me.top_role
            )

            # ── [SAFE-ANTI 2.0] ANTI-MASS MENTION ───────────────────────
            # BẮT BUỘC kiểm tra cờ Anti trong DB trước khi xử lý.
            # Nếu antinuke = 0 (đã tắt), bỏ qua toàn bộ khối này.
            if can_be_actioned and get_anti_setting(guild.id, "antinuke") == 1:
                total_mentions = len(message.mentions) + len(message.role_mentions)
                if total_mentions > _MASS_MENTION_THRESHOLD:
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass

                    timeout_until = discord.utils.utcnow() + timedelta(minutes=_MASS_MENTION_TIMEOUT_MIN)
                    try:
                        await author.timeout(
                            timeout_until,
                            reason=f"[{_BRAND}] Anti-Mass Mention — {total_mentions} mention trong 1 tin"
                        )
                    except (discord.Forbidden, discord.HTTPException) as e:
                        logger.warning(f"[AntiMassMention] Timeout thất bại: {e}")

                    # ── Log vào kênh log ──────────────────────────────────
                    ch = _get_log_channel(guild)
                    embed = discord.Embed(
                        title=f"{_ICO_STOP}  ANTI-MASS MENTION — Đã xử lý",
                        description=(
                            f"{_DIVIDER}\n"
                            f"> **Đối tượng:** {author.mention} (`{author}`)\n"
                            f"> **Số mention:** `{total_mentions}` (ngưỡng: `{_MASS_MENTION_THRESHOLD}`)\n"
                            f"> **Hình phạt:** {_ICO_LOCK} Timeout **{_MASS_MENTION_TIMEOUT_MIN} phút**\n"
                            f"> **Kênh:** {message.channel.mention}\n"
                            f"{_DIVIDER}\n"
                            f"> *{_BRAND} · Anti-Mass Mention Module*"
                        ),
                        color=_CLR_MENTION,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_footer(text=f"{_BRAND} · Anti-Mass Mention · Guild: {guild.id}")
                    await _safe_send(ch, embed=embed)

                    # ── Channel Notification (kênh vi phạm) ──────────────
                    await _notify_violation_channel(
                        channel=message.channel,
                        user=author,
                        violation_type="Anti-Mass Mention",
                        action_taken=(
                            f"Tin nhắn đã bị **xóa** và bạn bị "
                            f"**Timeout {_MASS_MENTION_TIMEOUT_MIN} phút**."
                        )
                    )

                    logger.info(
                        f"[AntiMassMention] Xử lý {author} ({author.id}) — "
                        f"{total_mentions} mention tại #{message.channel.name} guild {guild.id}."
                    )
                    return

            # ── [SAFE-ANTI 2.0] ANTI-EMOJI / STICKER SPAM ───────────────
            # BẮT BUỘC kiểm tra cờ Anti trong DB trước khi xử lý.
            # Nếu antinuke = 0 (đã tắt), bỏ qua toàn bộ khối này.
            if can_be_actioned and get_anti_setting(guild.id, "antinuke") == 1:
                emoji_count   = _count_emoji(message.content)
                sticker_count = len(message.stickers)
                total_visual  = emoji_count + sticker_count

                if total_visual > _EMOJI_SPAM_THRESHOLD:
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass

                    timeout_until = discord.utils.utcnow() + timedelta(minutes=_EMOJI_TIMEOUT_MIN)
                    try:
                        await author.timeout(
                            timeout_until,
                            reason=f"[{_BRAND}] Anti-Emoji Spam — {total_visual} emoji/sticker trong 1 tin"
                        )
                    except (discord.Forbidden, discord.HTTPException) as e:
                        logger.warning(f"[AntiEmojiSpam] Timeout thất bại: {e}")

                    # ── Log vào kênh log ──────────────────────────────────
                    ch = _get_log_channel(guild)
                    embed = discord.Embed(
                        title=f"{_ICO_STOP}  ANTI-EMOJI/STICKER SPAM — Đã xử lý",
                        description=(
                            f"{_DIVIDER}\n"
                            f"> **Đối tượng:** {author.mention} (`{author}`)\n"
                            f"> **Emoji phát hiện:** `{emoji_count}` emoji · `{sticker_count}` sticker\n"
                            f"> **Tổng cộng:** `{total_visual}` (ngưỡng: `{_EMOJI_SPAM_THRESHOLD}`)\n"
                            f"> **Hình phạt:** {_ICO_LOCK} Timeout **{_EMOJI_TIMEOUT_MIN} phút**\n"
                            f"> **Kênh:** {message.channel.mention}\n"
                            f"{_DIVIDER}\n"
                            f"> *{_BRAND} · Anti-Emoji Spam Module*"
                        ),
                        color=_CLR_EMOJI,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_footer(text=f"{_BRAND} · Anti-Emoji Spam · Guild: {guild.id}")
                    await _safe_send(ch, embed=embed)

                    # ── Channel Notification (kênh vi phạm) ──────────────
                    await _notify_violation_channel(
                        channel=message.channel,
                        user=author,
                        violation_type="Anti-Emoji/Sticker Spam",
                        action_taken=(
                            f"Tin nhắn đã bị **xóa** và bạn bị "
                            f"**Timeout {_EMOJI_TIMEOUT_MIN} phút**."
                        )
                    )

                    logger.info(
                        f"[AntiEmojiSpam] Xử lý {author} ({author.id}) — "
                        f"{total_visual} emoji/sticker tại #{message.channel.name} guild {guild.id}."
                    )
                    return

            # ── [ANTI SPAM FALLBACK] ─────────────────────────────────────
            if not is_protected_author and get_anti_setting(guild.id, "antispam") == 1:
                if can_be_actioned:
                    now = datetime.now(timezone.utc)
                    user_id = author.id

                    async with self._spam_times_lock:
                        last_ts = self.user_last_msg_times.get(user_id)
                        self.user_last_msg_times[user_id] = now

                    if last_ts is not None:
                        interval = (now - last_ts).total_seconds()
                        if interval < 1.0:
                            try:
                                await author.timeout(
                                    discord.utils.utcnow() + timedelta(hours=7),
                                    reason="[AntiSpam Fallback] Gửi tin nhắn quá nhanh (< 1.0s/tin)"
                                )
                                # ── Log vào kênh log ──────────────────────
                                log_embed = discord.Embed(
                                    title=f"{_ICO_CHAT}  ANTI-SPAM — Vi phạm tốc độ gửi tin",
                                    description=(
                                        f"{_DIVIDER}\n"
                                        f"> **Đối tượng:** {author.mention} (`{author}`)\n"
                                        f"> **Hành vi:** Gửi liên tục dưới `1.0 giây/tin`\n"
                                        f"> **Hình phạt:** {_ICO_LOCK} Timeout **7 giờ**\n"
                                        f"{_DIVIDER}\n"
                                        f"> *{_BRAND} · Anti-Spam Fallback Module*"
                                    ),
                                    color=_CLR_DANGER
                                )
                                ch = _get_log_channel(guild)
                                await _safe_send(ch, embed=log_embed)

                                # ── Channel Notification (kênh vi phạm) ──
                                await _notify_violation_channel(
                                    channel=message.channel,
                                    user=author,
                                    violation_type="Anti-Spam",
                                    action_taken="Bạn đã bị **Timeout 7 giờ** do gửi tin nhắn quá nhanh."
                                )
                                return
                            except discord.Forbidden:
                                pass
                            except discord.HTTPException as e:
                                logger.error(f"[AntiSpam][Fallback] Timeout lỗi: {e}")

            # ── [ANTI LINK FALLBACK + DISTRIBUTED SPAM DETECTOR] ────────
            if not is_protected_author and get_anti_setting(guild.id, "antilink") == 1:
                if can_be_actioned:
                    has_link = (
                        bool(re.search(r"h?ttps?://[^\s]+", message.content))
                        or "discord.gg/" in message.content
                    )
                    has_mention_everyone = message.mention_everyone

                    if has_link or has_mention_everyone:
                        channel_id = message.channel.id
                        now_mono   = time.monotonic()
                        cutoff     = now_mono - self.LINK_SPAM_WINDOW

                        async with self._link_spam_lock:
                            dq = self._link_spam_events[channel_id]
                            while dq and dq[0] <= cutoff:
                                dq.popleft()
                            dq.append(now_mono)
                            current_count = len(dq)
                            should_purge  = current_count >= self.LINK_SPAM_THRESHOLD

                            if should_purge:
                                dq.clear()
                                del self._link_spam_events[channel_id]

                        if should_purge:
                            await self._log_phase1_detection(
                                guild=guild,
                                event_type="Link-Spam / Mention-Everyone Phân Tán",
                                event_count=current_count,
                                window_seconds=self.LINK_SPAM_WINDOW,
                                source=f"Anti-Link Distributed Detector (#{message.channel.name})"
                            )
                            logger.warning(
                                f"[AntiLink] Phát hiện link-spam phân tán tại kênh "
                                f"#{message.channel.name} ({channel_id}) trong guild {guild.id}. "
                                f"Đang purge toàn kênh..."
                            )
                            try:
                                deleted = await message.channel.purge(
                                    limit=100,
                                    reason="[AntiLink] Phát hiện link-spam phân tán từ nhiều self-bot"
                                )
                                purge_embed = discord.Embed(
                                    title=f"{_ICO_STOP}  ALERT — Link-Spam Phân Tán Bị Đánh Chặn",
                                    description=(
                                        f"{_DIVIDER}\n"
                                        f"> **Kênh:** {message.channel.mention}\n"
                                        f"> **Ngưỡng phát hiện:** `{self.LINK_SPAM_THRESHOLD}` link/mention trong `{self.LINK_SPAM_WINDOW}s`\n"
                                        f"> **Tin nhắn đã xóa:** `{len(deleted)}`\n"
                                        f"{_DIVIDER}\n"
                                        f"> {_ICO_STOP} Dấu hiệu tấn công phân tán từ nhiều self-bot.\n"
                                        f"> *{_BRAND} · Anti-Link Distributed Purge*"
                                    ),
                                    color=_CLR_PURGE,
                                    timestamp=datetime.now(timezone.utc)
                                )
                                # Thông báo về kênh vi phạm (dạng public alert)
                                try:
                                    await message.channel.send(embed=purge_embed)
                                except (discord.Forbidden, discord.HTTPException):
                                    pass
                            except discord.Forbidden:
                                logger.warning(f"[AntiLink] Không đủ quyền purge kênh {channel_id}.")
                            except discord.HTTPException as e:
                                logger.error(f"[AntiLink] Lỗi HTTP khi purge kênh: {e}")
                            return

                        try:
                            await message.delete()
                        except discord.Forbidden:
                            pass
                        except discord.HTTPException as e:
                            logger.error(f"[AntiLink][Fallback] Xóa tin nhắn lỗi: {e}")

                        moderation_cog = self.bot.get_cog("ModerationCog")
                        if moderation_cog is not None:
                            warn_embed = await moderation_cog._handle_warn(
                                guild, author,
                                reason="[AntiLink Fallback] Gửi liên kết khi chưa được cấp quyền"
                            )
                        else:
                            logger.warning(
                                "[AntiLink][Fallback] Không tìm thấy ModerationCog để áp dụng cảnh báo."
                            )
                            warn_embed = discord.Embed(
                                description=(
                                    f"{_ICO_STOP} Không thể áp dụng cảnh báo tự động "
                                    f"(ModerationCog chưa được tải)."
                                ),
                                color=_CLR_DANGER
                            )
                        # ── Log vào kênh log ──────────────────────────────
                        log_embed = discord.Embed(
                            title=f"{_ICO_LINK}  ANTI-LINK — Liên kết trái phép bị chặn",
                            description=(
                                f"{_DIVIDER}\n"
                                f"> **Đối tượng:** {author.mention} (`{author}`)\n"
                                f"> **Hành vi:** Phát tán liên kết khi chưa được cấp quyền\n"
                                f"{_DIVIDER}\n"
                                f"{warn_embed.description}\n"
                                f"{_DIVIDER}\n"
                                f"> *{_BRAND} · Anti-Link Fallback Module*"
                            ),
                            color=_CLR_DANGER
                        )
                        ch = _get_log_channel(guild)
                        await _safe_send(ch, embed=log_embed)

                        # ── Channel Notification (kênh vi phạm) ──────────
                        await _notify_violation_channel(
                            channel=message.channel,
                            user=author,
                            violation_type="Anti-Link",
                            action_taken="Tin nhắn chứa liên kết đã bị **xóa** và bạn nhận thêm một cảnh báo."
                        )
                        return

        # [TRÒ CHƠI NỐI TỪ] — Uỷ quyền cho GameCog xử lý
        game_cog = self.bot.cogs.get("GameCog")
        if game_cog:
            handled = await game_cog.handle_noitu_message(message)
            if handled:
                return

    # =========================================================================
    # [SAFE-ANTI 2.0] ACCOUNT AGE FILTER — on_member_join (mở rộng)
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        Xử lý sự kiện thành viên gia nhập server.

        [SAFE-ANTI 2.0 — Account Age Filter]
        Nếu tài khoản < 7 ngày tuổi:
          → Tính thời gian còn thiếu (đến đủ 7 ngày kể từ lúc tạo tài khoản)
          → Timeout thành viên đúng khoảng thời gian còn thiếu đó
          → Gửi log vào log channel

        [Cũ — Anti-Bot Raid Detection]
        Nếu thành viên là Bot và Anti-Nuke bật:
          → Theo dõi tần suất bot join và xử lý bot raid nếu vượt ngưỡng.
        """
        guild = member.guild

        # ── [SAFE-ANTI 2.0] ACCOUNT AGE FILTER ──────────────────────────
        # BẮT BUỘC kiểm tra cờ antinuke trong DB trước khi xử lý.
        # Nếu antinuke = 0 (đã tắt), bỏ qua toàn bộ khối Account Age Filter —
        # không được timeout thành viên mới dù tài khoản quá mới.
        if not member.bot and get_anti_setting(guild.id, "antinuke") == 1:
            account_age = datetime.now(timezone.utc) - member.created_at
            if account_age < timedelta(days=_ACCOUNT_AGE_DAYS):
                # Thời gian còn thiếu để đủ 7 ngày (tính từ khi tạo tài khoản)
                remaining = timedelta(days=_ACCOUNT_AGE_DAYS) - account_age
                timeout_until = discord.utils.utcnow() + remaining

                days_remaining  = remaining.days
                hours_remaining = remaining.seconds // 3600
                mins_remaining  = (remaining.seconds % 3600) // 60

                can_timeout = (
                    guild.me is not None
                    and member.top_role < guild.me.top_role
                )

                if can_timeout:
                    try:
                        await member.timeout(
                            timeout_until,
                            reason=(
                                f"[{_BRAND}] Account Age Filter — tài khoản chỉ "
                                f"{int(account_age.total_seconds() // 86400)} ngày tuổi "
                                f"(yêu cầu: {_ACCOUNT_AGE_DAYS} ngày)"
                            )
                        )
                    except (discord.Forbidden, discord.HTTPException) as e:
                        logger.warning(
                            f"[AntiAge] Không thể timeout {member} ({member.id}) "
                            f"tại guild {guild.id}: {e}"
                        )

                ch = _get_log_channel(guild)
                embed = discord.Embed(
                    title=f"{_ICO_LOCK}  ACCOUNT AGE FILTER — Tài khoản quá mới",
                    description=(
                        f"{_DIVIDER}\n"
                        f"> Thành viên mới vừa tham gia với tài khoản chưa đủ tuổi.\n"
                        f"{_DIVIDER}"
                    ),
                    color=_CLR_AGE,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name=f"{_ICO_RESULT} Thông tin thành viên",
                    value=(
                        f"> **Tài khoản:** {member.mention} (`{member}`)\n"
                        f"> **ID:** `{member.id}`\n"
                        f"> **Tuổi tài khoản:** `{int(account_age.total_seconds() // 86400)}` ngày "
                        f"`{int((account_age.total_seconds() % 86400) // 3600)}` giờ\n"
                        f"> **Yêu cầu tối thiểu:** `{_ACCOUNT_AGE_DAYS}` ngày"
                    ),
                    inline=False
                )
                embed.add_field(
                    name=f"{_ICO_TIME} Trạng thái Timeout",
                    value=(
                        f"> **Thời gian còn thiếu:** `{days_remaining}` ngày "
                        f"`{hours_remaining}` giờ `{mins_remaining}` phút\n"
                        f"> **Timeout đến:** <t:{int(timeout_until.timestamp())}:F>\n"
                        f"> **Hành động:** {_ICO_LOCK} Tự động mute đến khi đủ `{_ACCOUNT_AGE_DAYS}` ngày"
                    ),
                    inline=False
                )
                embed.set_footer(text=f"{_BRAND} · Account Age Filter · Guild: {guild.id}")
                await _safe_send(ch, embed=embed)

                logger.info(
                    f"[AntiAge] Timeout {member} ({member.id}) — tài khoản "
                    f"{int(account_age.total_seconds() // 86400)} ngày tuổi. "
                    f"Còn {days_remaining}d {hours_remaining}h {mins_remaining}m."
                )
                return  # Không xử lý tiếp bot-raid cho thành viên thường đã được xử lý

        # ── [CŨ] ANTI-BOT RAID DETECTION ────────────────────────────────
        if not member.bot:
            return

        if get_anti_setting(guild.id, "antinuke") != 1:
            return

        now_mono = time.monotonic()
        cutoff = now_mono - self.BOT_RAID_WINDOW

        async with self._bot_raid_lock:
            dq = self._bot_join_events[guild.id]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            dq.append(now_mono)
            bot_join_count = len(dq)
            is_bot_raid = bot_join_count >= self.BOT_RAID_THRESHOLD

            if is_bot_raid:
                dq.clear()

        if not is_bot_raid:
            return

        logger.warning(
            f"[AntiBotRaid] {bot_join_count} bots joined guild '{guild.name}' ({guild.id}) "
            f"within {self.BOT_RAID_WINDOW}s — BOT RAID DETECTED. Responding..."
        )

        ch = _get_log_channel(guild)
        if ch:
            alert_embed = discord.Embed(
                title=f"{_ICO_STOP}  BOT RAID DETECTED — Đang xử lý...",
                description=(
                    f"> Phát hiện **{bot_join_count} bot** gia nhập server trong "
                    f"`{self.BOT_RAID_WINDOW}s`.\n"
                    f"> Đang tự động kick/ban các bot xâm nhập...\n"
                    f"{_DIVIDER}"
                ),
                color=_CLR_BOT_RAID,
                timestamp=datetime.now(timezone.utc)
            )
            alert_embed.set_footer(text=f"{_BRAND} · Anti-Bot Raid · Guild: {guild.id}")
            await _safe_send(ch, embed=alert_embed)

        kicked_bots: list[str] = []
        banned_bots: list[str] = []

        wave_bots: list[discord.Member] = [
            m for m in guild.members
            if m.bot and m.id != self.bot.user.id
            and m.joined_at is not None
            and (datetime.now(timezone.utc) - m.joined_at).total_seconds() <= self.BOT_RAID_WINDOW
        ]

        if member not in wave_bots:
            wave_bots.append(member)

        for bot_member in wave_bots:
            if bot_member.id == self.bot.user.id:
                continue
            try:
                await bot_member.kick(
                    reason=f"[{_BRAND}] Bot Raid — automatic kick during bot raid response"
                )
                kicked_bots.append(str(bot_member))
                logger.info(f"[AntiBotRaid] Kicked bot {bot_member} ({bot_member.id}) from guild {guild.id}.")
            except discord.Forbidden:
                try:
                    await guild.ban(
                        bot_member,
                        reason=f"[{_BRAND}] Bot Raid — kick failed, escalated to ban",
                        delete_message_days=0
                    )
                    banned_bots.append(str(bot_member))
                    logger.info(f"[AntiBotRaid] Banned bot {bot_member} ({bot_member.id}) from guild {guild.id}.")
                except (discord.Forbidden, discord.HTTPException) as e:
                    logger.warning(
                        f"[AntiBotRaid] Cannot kick or ban bot {bot_member} at guild {guild.id}: {e}"
                    )
            except discord.HTTPException as e:
                logger.error(f"[AntiBotRaid] HTTP error kicking bot {bot_member}: {e}")

        if ch:
            result_embed = discord.Embed(
                title=f"{_ICO_TICK}  BOT RAID RESPONSE HOÀN TẤT",
                description=(
                    f"> Hệ thống **{_BRAND}** đã xử lý bot raid thành công.\n"
                    f"{_DIVIDER}"
                ),
                color=_CLR_BOT_RAID,
                timestamp=datetime.now(timezone.utc)
            )
            result_embed.add_field(
                name=f"{_ICO_RESULT} Kết quả",
                value=(
                    f"> **Bot bị phát hiện:** `{len(wave_bots)}`\n"
                    f"> **Đã kick:** `{len(kicked_bots)}`\n"
                    f"> **Đã ban (escalated):** `{len(banned_bots)}`\n"
                    f"> **Ngưỡng kích hoạt:** `{bot_join_count}` bots / `{self.BOT_RAID_WINDOW}s`"
                ),
                inline=False
            )
            if kicked_bots or banned_bots:
                removed_list = "\n".join(
                    [f"> {_ICO_TICK} `{b}` (kicked)" for b in kicked_bots[:10]]
                    + [f"> {_ICO_STOP} `{b}` (banned)" for b in banned_bots[:5]]
                )
                result_embed.add_field(
                    name=f"{_ICO_SHIELD} Danh sách bot đã xử lý",
                    value=removed_list[:1000],
                    inline=False
                )
            result_embed.set_footer(text=f"{_BRAND} · Anti-Bot Raid Complete · Guild: {guild.id}")
            await _safe_send(ch, embed=result_embed)

    # =========================================================================
    # [SAFE-ANTI 2.0] ANTI-WEBHOOK — on_webhooks_update
    # =========================================================================
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """
        [SAFE-ANTI 2.0] Phát hiện và xóa Webhook mới được tạo trái phép.

        Cơ chế:
          1. Lấy danh sách webhooks hiện tại trong kênh vừa có sự thay đổi.
          2. Kiểm tra Audit Log để xác định ai vừa tạo webhook.
          3. Nếu người tạo KHÔNG phải Server Owner và KHÔNG phải Bot → Xóa webhook ngay.
          4. Gửi log Phase 1 (phát hiện) và Phase 3 (hoàn tất) vào log channel.
          5. Áp dụng bẫy Hierarchy Bypass nếu cần.

        Ngoại trừ:
          - Server Owner: có quyền tạo webhook tự do.
          - Bot (self.bot.user.id): webhook do bot tự tạo không bị xóa.
        """
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild

        if get_anti_setting(guild.id, "antinuke") != 1:
            return

        # Lấy audit log để xác định ai vừa tạo webhook
        creator: typing.Optional[discord.Member] = None
        webhook_name: str = "Unknown"

        try:
            async for entry in guild.audit_logs(
                limit=5,
                action=discord.AuditLogAction.webhook_create
            ):
                # Chỉ lấy entry trong vòng 10 giây gần nhất để tránh false positive
                age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                if age > 10:
                    break

                if entry.target and hasattr(entry.target, "channel") and entry.target.channel:
                    if entry.target.channel.id != channel.id:
                        continue

                creator = guild.get_member(entry.user.id)
                if creator is None:
                    try:
                        creator = await guild.fetch_member(entry.user.id)
                    except (discord.NotFound, discord.HTTPException):
                        creator = None

                if entry.target and hasattr(entry.target, "name"):
                    webhook_name = entry.target.name or "Unknown"

                break
        except discord.Forbidden:
            logger.warning(f"[AntiWebhook] Thiếu quyền xem Audit Log tại guild {guild.id}.")
        except discord.HTTPException as e:
            logger.error(f"[AntiWebhook] Lỗi HTTP khi đọc Audit Log: {e}")

        # Nếu không xác định được người tạo, vẫn xóa webhook mới nhất trong kênh
        # (an toàn hơn là bỏ qua)
        if creator is not None:
            # Ngoại trừ Server Owner và chính Bot
            if creator.id == guild.owner_id or creator.id == self.bot.user.id:
                logger.debug(
                    f"[AntiWebhook] Webhook '{webhook_name}' được tạo bởi "
                    f"{'Owner' if creator.id == guild.owner_id else 'Bot'} — bỏ qua."
                )
                return

        # Phase 1: Thông báo phát hiện
        await self._log_phase1_detection(
            guild=guild,
            event_type="Webhook Trái Phép Được Tạo",
            event_count=1,
            window_seconds=10.0,
            source=f"Anti-Webhook (#{channel.name})"
        )

        # Lấy và xóa tất cả webhook mới trong kênh không thuộc về Bot
        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            logger.warning(f"[AntiWebhook] Thiếu quyền xem webhooks tại #{channel.name} guild {guild.id}.")
            return
        except discord.HTTPException as e:
            logger.error(f"[AntiWebhook] Lỗi HTTP khi lấy webhooks: {e}")
            return

        deleted_count = 0
        for wh in webhooks:
            # Bỏ qua webhook do Bot tạo
            if wh.user and wh.user.id == self.bot.user.id:
                continue
            # Bỏ qua webhook do Owner tạo
            if wh.user and wh.user.id == guild.owner_id:
                continue

            try:
                await wh.delete(reason=f"[{_BRAND}] Anti-Webhook — webhook trái phép bị xóa tự động")
                deleted_count += 1
                logger.info(
                    f"[AntiWebhook] Đã xóa webhook '{wh.name}' (ID: {wh.id}) "
                    f"tại #{channel.name} guild {guild.id}."
                )
            except discord.Forbidden:
                logger.warning(f"[AntiWebhook] Thiếu quyền xóa webhook '{wh.name}'.")
            except discord.HTTPException as e:
                logger.error(f"[AntiWebhook] Lỗi HTTP khi xóa webhook '{wh.name}': {e}")

        if deleted_count == 0:
            return  # Không có webhook nào bị xóa — false positive, không log thêm

        # Xử lý Hierarchy Bypass nếu biết người tạo
        if creator is not None and guild.me is not None:
            if creator.top_role >= guild.me.top_role:
                await self._alert_owner_hierarchy_bypass(
                    guild=guild,
                    attacker=creator,
                    event_description=(
                        f"Tạo Webhook trái phép `{webhook_name}` tại #{channel.name} "
                        f"(đã bị xóa — {deleted_count} webhook)"
                    )
                )
            else:
                # Ghi log vi phạm của creator
                ch = _get_log_channel(guild)
                embed = discord.Embed(
                    title=f"{_ICO_SHIELD}  ANTI-WEBHOOK — Webhook Trái Phép Bị Xóa",
                    description=(
                        f"{_DIVIDER}\n"
                        f"> Phát hiện **webhook trái phép** vừa được tạo và đã tự động xóa.\n"
                        f"{_DIVIDER}"
                    ),
                    color=_CLR_WEBHOOK,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name=f"{_ICO_RESULT} Chi tiết",
                    value=(
                        f"> **Người tạo:** {creator.mention} (`{creator}`)\n"
                        f"> **Tên webhook:** `{webhook_name}`\n"
                        f"> **Kênh:** {channel.mention}\n"
                        f"> **Số webhook đã xóa:** `{deleted_count}`"
                    ),
                    inline=False
                )
                embed.add_field(
                    name=f"{_ICO_TICK} Kết quả",
                    value=(
                        f"> {_ICO_TICK} Đã xóa `{deleted_count}` webhook vi phạm\n"
                        f"> *{_BRAND} · Anti-Webhook Module*"
                    ),
                    inline=False
                )
                embed.set_footer(text=f"{_BRAND} · Anti-Webhook · Guild: {guild.id}")
                await _safe_send(ch, embed=embed)
        else:
            # Không xác định được creator — vẫn log kết quả
            ch = _get_log_channel(guild)
            embed = discord.Embed(
                title=f"{_ICO_SHIELD}  ANTI-WEBHOOK — Webhook Không Rõ Nguồn Bị Xóa",
                description=(
                    f"{_DIVIDER}\n"
                    f"> Phát hiện webhook mới tại {channel.mention} (không xác định được người tạo).\n"
                    f"> Đã tự động xóa `{deleted_count}` webhook.\n"
                    f"{_DIVIDER}\n"
                    f"> *{_BRAND} · Anti-Webhook Module*"
                ),
                color=_CLR_WEBHOOK,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"{_BRAND} · Anti-Webhook · Guild: {guild.id}")
            await _safe_send(ch, embed=embed)

    # =========================================================================
    # [SAFE-ANTI 2.0] ANTI-CHANNEL RENAME — on_guild_channel_update
    # =========================================================================
    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel
    ) -> None:
        """
        [SAFE-ANTI 2.0] Phát hiện đổi tên / topic kênh trái phép và khôi phục.

        Cơ chế:
          1. So sánh name và topic của kênh trước và sau khi cập nhật.
          2. Nếu có thay đổi → Kiểm tra Audit Log để xác định người thực hiện.
          3. Nếu người đổi KHÔNG phải Server Owner / Bot → Khôi phục tên/topic cũ.
          4. Tước quyền `Manage Channels` của người đó (trừ Server Owner).
          5. Cập nhật cache sang tên/topic mới nếu thay đổi hợp lệ (do Owner/Bot).
          6. Gửi log đầy đủ vào log channel.

        Bẫy Hierarchy Bypass:
          Nếu người đổi có role >= Bot → không thể tước quyền trực tiếp →
          Tag Owner khẩn cấp + vẫn khôi phục tên/topic nếu có thể.
        """
        if not isinstance(after, (discord.TextChannel, discord.VoiceChannel,
                                   discord.StageChannel, discord.ForumChannel)):
            return

        guild = after.guild

        if get_anti_setting(guild.id, "antinuke") != 1:
            return

        # Lấy dữ liệu cũ từ cache
        async with self._channel_cache_lock:
            cached = self._channel_info_cache.get(before.id)

        old_name  = cached["name"]  if cached else before.name
        old_topic = cached["topic"] if cached else getattr(before, "topic", None)
        new_name  = after.name
        new_topic = getattr(after, "topic", None)

        name_changed  = old_name != new_name
        topic_changed = old_topic != new_topic

        if not name_changed and not topic_changed:
            # Không có thay đổi tên/topic — cập nhật cache với thông tin hiện tại và thoát
            async with self._channel_cache_lock:
                self._channel_info_cache[after.id] = {
                    "name": new_name,
                    "topic": new_topic
                }
            return

        # Xác định người thực hiện qua Audit Log
        editor: typing.Optional[discord.Member] = None
        try:
            async for entry in guild.audit_logs(
                limit=5,
                action=discord.AuditLogAction.channel_update
            ):
                age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                if age > 10:
                    break
                if entry.target and entry.target.id == after.id:
                    editor = guild.get_member(entry.user.id)
                    if editor is None:
                        try:
                            editor = await guild.fetch_member(entry.user.id)
                        except (discord.NotFound, discord.HTTPException):
                            pass
                    break
        except discord.Forbidden:
            logger.warning(f"[AntiRename] Thiếu quyền xem Audit Log tại guild {guild.id}.")
        except discord.HTTPException as e:
            logger.error(f"[AntiRename] Lỗi HTTP khi đọc Audit Log: {e}")

        # Ngoại trừ: Server Owner và Bot
        is_legitimate = (
            editor is not None
            and (editor.id == guild.owner_id or editor.id == self.bot.user.id)
        )

        if is_legitimate:
            # Thay đổi hợp lệ — cập nhật cache với tên/topic mới
            async with self._channel_cache_lock:
                self._channel_info_cache[after.id] = {
                    "name": new_name,
                    "topic": new_topic
                }
            logger.debug(
                f"[AntiRename] Kênh #{after.name} được đổi bởi "
                f"{'Owner' if editor.id == guild.owner_id else 'Bot'} — hợp lệ, cập nhật cache."
            )
            return

        # Thay đổi KHÔNG hợp lệ → Khôi phục
        logger.warning(
            f"[AntiRename] Kênh #{old_name} bị đổi thành #{new_name} "
            f"bởi {editor} ({editor.id if editor else 'Unknown'}) tại guild {guild.id}. "
            f"Đang khôi phục..."
        )

        # Cố gắng khôi phục tên và topic
        restore_kwargs: dict = {}
        if name_changed:
            restore_kwargs["name"] = old_name
        if topic_changed and isinstance(after, discord.TextChannel):
            restore_kwargs["topic"] = old_topic

        restored = False
        if restore_kwargs and guild.me is not None:
            try:
                await after.edit(
                    **restore_kwargs,
                    reason=f"[{_BRAND}] Anti-Channel Rename — khôi phục tên/topic bị thay đổi trái phép"
                )
                restored = True
                logger.info(
                    f"[AntiRename] Đã khôi phục kênh: "
                    f"'{old_name}' (topic: {old_topic!r}) tại guild {guild.id}."
                )
            except discord.Forbidden:
                logger.warning(f"[AntiRename] Thiếu quyền khôi phục kênh #{after.name}.")
            except discord.HTTPException as e:
                logger.error(f"[AntiRename] Lỗi HTTP khi khôi phục kênh: {e}")

        # Xử lý Hierarchy Bypass
        if editor is not None and guild.me is not None:
            if editor.top_role >= guild.me.top_role:
                await self._alert_owner_hierarchy_bypass(
                    guild=guild,
                    attacker=editor,
                    event_description=(
                        f"Đổi tên/topic kênh `#{old_name}` → `#{new_name}` "
                        f"({'đã khôi phục' if restored else 'chưa khôi phục được'})"
                    )
                )
            else:
                # Tước quyền Manage Channels của người đổi
                try:
                    overwrite = after.overwrites_for(editor)
                    overwrite.manage_channels = False
                    await after.set_permissions(
                        editor,
                        overwrite=overwrite,
                        reason=f"[{_BRAND}] Anti-Channel Rename — tước Manage Channels"
                    )
                    logger.info(
                        f"[AntiRename] Đã tước quyền Manage Channels của "
                        f"{editor} ({editor.id}) tại kênh #{after.name} guild {guild.id}."
                    )
                except discord.Forbidden:
                    logger.warning(
                        f"[AntiRename] Thiếu quyền để tước Manage Channels của {editor}."
                    )
                except discord.HTTPException as e:
                    logger.error(f"[AntiRename] Lỗi HTTP khi tước Manage Channels: {e}")

        # Gửi log
        change_details: list[str] = []
        if name_changed:
            change_details.append(f"> **Tên cũ:** `{old_name}` → **Tên mới:** `{new_name}`")
        if topic_changed:
            old_t_display = f"`{old_topic[:50]}...`" if old_topic and len(old_topic) > 50 else f"`{old_topic}`"
            new_t_display = f"`{new_topic[:50]}...`" if new_topic and len(new_topic) > 50 else f"`{new_topic}`"
            change_details.append(f"> **Topic cũ:** {old_t_display} → **Topic mới:** {new_t_display}")

        ch = _get_log_channel(guild)
        embed = discord.Embed(
            title=f"{_ICO_SHIELD}  ANTI-CHANNEL RENAME — {'Đã Khôi Phục' if restored else 'Phát Hiện Vi Phạm'}",
            description=(
                f"{_DIVIDER}\n"
                f"> Phát hiện thay đổi tên/topic kênh trái phép.\n"
                f"{_DIVIDER}"
            ),
            color=_CLR_RENAME,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name=f"{_ICO_RESULT} Chi tiết thay đổi",
            value="\n".join(change_details) if change_details else "> `Không rõ`",
            inline=False
        )
        if editor is not None:
            embed.add_field(
                name=f"{_ICO_STOP} Người thực hiện",
                value=(
                    f"> **Tài khoản:** {editor.mention} (`{editor}`)\n"
                    f"> **ID:** `{editor.id}`"
                ),
                inline=False
            )
        embed.add_field(
            name=f"{_ICO_TICK} Hành động tự động",
            value=(
                f"> {_ICO_TICK if restored else _ICO_STOP} **Khôi phục tên/topic:** "
                f"{'Thành công' if restored else 'Thất bại (thiếu quyền)'}\n"
                f"> {_ICO_LOCK} **Tước `Manage Channels`:** "
                f"{'Đã thực hiện' if editor and guild.me and editor.top_role < guild.me.top_role else 'Không thể (hierarchy bypass)'}\n"
                f"> *{_BRAND} · Anti-Channel Rename Module*"
            ),
            inline=False
        )
        embed.set_footer(text=f"{_BRAND} · Anti-Channel Rename · Guild: {guild.id}")
        await _safe_send(ch, embed=embed)

    # =========================================================================
    # on_guild_channel_create: cập nhật cache kênh mới
    # =========================================================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Khi kênh mới được tạo, lưu thông tin vào cache để Anti-Channel Rename theo dõi."""
        if isinstance(channel, (discord.TextChannel, discord.VoiceChannel,
                                 discord.StageChannel, discord.ForumChannel)):
            async with self._channel_cache_lock:
                self._channel_info_cache[channel.id] = {
                    "name": channel.name,
                    "topic": getattr(channel, "topic", None)
                }

    # =========================================================================
    # on_guild_channel_delete: dọn cache kênh đã xóa
    # =========================================================================
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """
        Xử lý sự kiện xóa kênh với 2 lớp bảo vệ (giữ nguyên logic gốc).
        Đồng thời dọn cache kênh đã bị xóa.
        """
        # Dọn cache kênh bị xóa
        async with self._channel_cache_lock:
            self._channel_info_cache.pop(channel.id, None)

        if get_anti_setting(channel.guild.id, "antinuke") != 1:
            return

        guild = channel.guild

        if await server_anti_nuke_limiter.is_rate_limited(guild.id):
            await self._log_phase1_detection(
                guild=guild,
                event_type="Xóa Kênh Hàng Loạt",
                event_count=server_anti_nuke_limiter.threshold,
                window_seconds=server_anti_nuke_limiter.window,
                source="GlobalRateLimiter (Proactive Layer 1)"
            )
            await self._trigger_lockdown(
                guild,
                reason=(
                    f"Phát hiện {server_anti_nuke_limiter.threshold} lần xóa kênh "
                    f"trong {server_anti_nuke_limiter.window}s — dấu hiệu tấn công phân tán (Audit Log bypass)."
                )
            )

        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                mod = entry.user
                if mod.id == self.bot.user.id or mod.id == guild.owner_id:
                    continue

                if mod.top_role >= guild.me.top_role:
                    await self._alert_owner_hierarchy_bypass(
                        guild=guild,
                        attacker=mod,
                        event_description=f"Xóa kênh `#{channel.name}` hàng loạt (Audit Log xác nhận)"
                    )
                    await self._trigger_lockdown(
                        guild,
                        reason=(
                            f"Tấn công từ {mod} (role cao hơn Bot) — xóa kênh #{channel.name}. "
                            f"Không thể kick/ban trực tiếp. Đã tag Owner và kích hoạt lockdown tối đa."
                        ),
                        hierarchy_bypass=True,
                        bypass_attacker=mod
                    )
                    continue

                if mod.top_role < guild.me.top_role:
                    try:
                        await mod.kick(reason="[AntiNuke] Tự ý xóa kênh hàng loạt.")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException as e:
                        logger.error(f"[AntiNuke] Lỗi HTTP khi kick thủ phạm xóa kênh: {e}")
        except discord.Forbidden:
            logger.warning(f"[AntiNuke] Thiếu quyền xem audit log tại server {guild.id}")
        except discord.HTTPException as e:
            logger.error(f"[AntiNuke] Lỗi HTTP khi đọc audit log (channel_delete): {e}")

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: typing.Union[discord.User, discord.Member]
    ) -> None:
        """
        Xử lý sự kiện ban thành viên với 2 lớp bảo vệ.
        Lớp 1 (Proactive): GlobalRateLimiter.
        Lớp 2 (Reactive): Audit Log fallback.
        Role Hierarchy Bypass: Tag Owner + Lockdown tối đa.
        """
        if get_anti_setting(guild.id, "antinuke") != 1:
            return

        if await server_anti_nuke_limiter.is_rate_limited(guild.id):
            await self._log_phase1_detection(
                guild=guild,
                event_type="Ban Hàng Loạt",
                event_count=server_anti_nuke_limiter.threshold,
                window_seconds=server_anti_nuke_limiter.window,
                source="GlobalRateLimiter (Proactive Layer 1)"
            )
            await self._trigger_lockdown(
                guild,
                reason=(
                    f"Phát hiện {server_anti_nuke_limiter.threshold} lần ban thành viên "
                    f"trong {server_anti_nuke_limiter.window}s — dấu hiệu tấn công phân tán (Audit Log bypass)."
                )
            )

        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                mod = entry.user
                if mod.id == self.bot.user.id or mod.id == guild.owner_id:
                    continue

                if mod.top_role >= guild.me.top_role:
                    await self._alert_owner_hierarchy_bypass(
                        guild=guild,
                        attacker=mod,
                        event_description=f"Ban hàng loạt thành viên (nạn nhân: `{user}`) — Audit Log xác nhận"
                    )
                    await self._trigger_lockdown(
                        guild,
                        reason=(
                            f"Tấn công từ {mod} (role cao hơn Bot) — ban hàng loạt, nạn nhân: {user}. "
                            f"Không thể kick/ban trực tiếp. Đã tag Owner và kích hoạt lockdown tối đa."
                        ),
                        hierarchy_bypass=True,
                        bypass_attacker=mod
                    )
                    continue

                if mod.top_role < guild.me.top_role:
                    try:
                        await mod.kick(reason="[AntiNuke] Tự ý cấm thành viên hàng loạt.")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException as e:
                        logger.error(f"[AntiNuke] Lỗi HTTP khi kick thủ phạm ban hàng loạt: {e}")
        except discord.Forbidden:
            logger.warning(f"[AntiNuke] Thiếu quyền xem audit log tại server {guild.id}")
        except discord.HTTPException as e:
            logger.error(f"[AntiNuke] Lỗi HTTP khi đọc audit log (member_ban): {e}")

    # =========================================================================
    # LỆNH BẬT ANTI — /anti_on và !anti_on
    # =========================================================================
    @app_commands.command(name="anti_on", description="[ADMIN] Mở bảng điều khiển BẬT hệ thống Anti bảo vệ server")
    @app_commands.guild_only()
    async def anti_on_slash(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction.user, interaction.guild):
            await interaction.response.send_message(
                embed=_build_cmd_perm_denied_embed(),
                ephemeral=True
            )
            return

        embed = _build_anti_status_embed(interaction.guild, mode="on")
        view  = AntiOnView()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @commands.command(name="anti_on")
    @commands.guild_only()
    async def anti_on_prefix(self, ctx: commands.Context) -> None:
        if not _is_admin(ctx.author, ctx.guild):
            await ctx.send(embed=_build_cmd_perm_denied_embed())
            return

        embed = _build_anti_status_embed(ctx.guild, mode="on")
        view  = AntiOnView()
        msg   = await ctx.send(embed=embed, view=view)
        view.message = msg

    # =========================================================================
    # LỆNH TẮT ANTI — /anti_off và !anti_off
    # =========================================================================
    @app_commands.command(name="anti_off", description="[ADMIN] Mở bảng điều khiển TẮT hệ thống Anti bảo vệ server")
    @app_commands.guild_only()
    async def anti_off_slash(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction.user, interaction.guild):
            await interaction.response.send_message(
                embed=_build_cmd_perm_denied_embed(),
                ephemeral=True
            )
            return

        embed = _build_anti_status_embed(interaction.guild, mode="off")
        view  = AntiOffView()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @commands.command(name="anti_off")
    @commands.guild_only()
    async def anti_off_prefix(self, ctx: commands.Context) -> None:
        if not _is_admin(ctx.author, ctx.guild):
            await ctx.send(embed=_build_cmd_perm_denied_embed())
            return

        embed = _build_anti_status_embed(ctx.guild, mode="off")
        view  = AntiOffView()
        msg   = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiCog(bot))
