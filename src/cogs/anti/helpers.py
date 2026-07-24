"""
cogs/anti/helpers.py — Các hàm phụ trợ nội bộ dùng chung trong module SAFE-ANTI 2.0.

Bao gồm:
  - _status_badge()              : Badge trạng thái inline Active/Offline
  - _get_log_channel()           : Tìm kênh log phù hợp theo thứ tự ưu tiên
  - _safe_send()                 : Gửi tin nhắn an toàn, nuốt lỗi Discord
  - _notify_violation_channel()  : Gửi embed cảnh báo trực tiếp tại kênh vi phạm
  - _build_anti_status_embed()   : Xây dựng embed trạng thái hệ thống Anti
  - _build_timeout_embed()       : Embed phiên điều khiển hết hạn
  - _build_perm_denied_embed()   : Embed từ chối quyền truy cập
  - _build_cmd_perm_denied_embed(): Embed từ chối quyền khi dùng lệnh
  - _is_admin()                  : Kiểm tra quyền admin
  - _count_emoji()               : Đếm emoji Unicode + Discord custom emoji
"""

import re
import typing
import logging
import discord
from datetime import datetime, timezone

from database import get_anti_setting

from .constants import (
    _BRAND, _DIVIDER,
    _CLR_SUCCESS, _CLR_DANGER, _CLR_WARN_CH,
    _ICO_SHIELD, _ICO_LINK, _ICO_CHAT, _ICO_STOP,
    _ICO_TICK, _ICO_RESULT, _ICO_TIME, _ICO_LOCK,
)

logger = logging.getLogger("AntiCog")


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


# ─────────────────────────────────────────────────────────────────────────
# HELPER: GỬI TIN NHẮN AN TOÀN
# ─────────────────────────────────────────────────────────────────────────
async def _safe_send(
    channel: typing.Optional[discord.TextChannel],
    **kwargs
) -> typing.Optional[discord.Message]:
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
        color=_CLR_TIMEOUT if False else 0x95A5A6
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
