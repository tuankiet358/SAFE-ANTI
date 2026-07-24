"""
cogs/anti/automod.py — Tích hợp Discord Native AutoMod API cho module SAFE-ANTI 2.0.

Bao gồm:
  - _find_automod_rule()              : Tìm AutoMod rule theo tên trong guild
  - _delete_automod_rule_by_name()    : Xóa AutoMod rule theo tên
  - _ensure_antilink_automod_rule()   : Tạo/cập nhật rule chặn liên kết
  - _ensure_antispam_automod_rule()   : Tạo/cập nhật rule chống spam mention
"""

import typing
import logging
import discord
from datetime import timedelta

from .constants import (
    _BRAND,
    _AUTOMOD_RULE_ANTILINK,
    _AUTOMOD_RULE_ANTISPAM,
)
from .helpers import _get_log_channel

logger = logging.getLogger("AntiCog")


# ─────────────────────────────────────────────────────────────────────────
# TÌM AUTOMOD RULE THEO TÊN
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


# ─────────────────────────────────────────────────────────────────────────
# XÓA AUTOMOD RULE THEO TÊN
# ─────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────
# TẠO / CẬP NHẬT AUTOMOD RULE ANTI-LINK
# ─────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────
# TẠO / CẬP NHẬT AUTOMOD RULE ANTI-SPAM
# ─────────────────────────────────────────────────────────────────────────
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
