"""
cogs/anti/ui.py — Select Menus và Views tương tác cho module SAFE-ANTI 2.0.

Bao gồm:
  - AntiOnSelect   : Select menu bật từng module Anti
  - AntiOnView     : View chứa AntiOnSelect, timeout 120 giây
  - AntiOffSelect  : Select menu tắt từng module Anti
  - AntiOffView    : View chứa AntiOffSelect, timeout 120 giây
"""

import discord
from database import update_anti_db

from .constants import (
    _BRAND, _DIVIDER,
    _ICO_SHIELD, _ICO_TICK, _ICO_STOP, _ICO_RESULT, _ICO_LOCK,
)
from .helpers import (
    _build_anti_status_embed,
    _build_timeout_embed,
    _build_perm_denied_embed,
)
from .automod import (
    _ensure_antilink_automod_rule,
    _ensure_antispam_automod_rule,
    _delete_automod_rule_by_name,
)
from .constants import _AUTOMOD_RULE_ANTILINK, _AUTOMOD_RULE_ANTISPAM


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
