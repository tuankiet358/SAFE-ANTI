"""
utils/embed.py — Helper tạo Discord Embed chuẩn dùng chung toàn bot.
Cung cấp các hàm tiện ích cho embed thành công, lỗi, và thông báo hệ thống.
"""

import discord
from datetime import datetime, timezone


def success_embed(title: str, description: str, color: int = 0x2ECC71) -> discord.Embed:
    """Tạo embed thông báo thành công."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    return embed


def error_embed(title: str, description: str, color: int = 0xE74C3C) -> discord.Embed:
    """Tạo embed thông báo lỗi."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    return embed


def info_embed(title: str, description: str, color: int = 0x3498DB) -> discord.Embed:
    """Tạo embed thông báo thông tin."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    return embed
