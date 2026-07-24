"""
cogs/anti/__init__.py — Entry point cho module SAFE-ANTI 2.0.
Discord.py gọi hàm setup() này khi load extension "cogs.anti".
"""

from discord.ext import commands
from .cog import AntiCog


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiCog(bot))
