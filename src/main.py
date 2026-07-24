"""
main.py — File khởi chạy Discord Bot
Tự động load tất cả extensions (Cogs) và khởi động bot.
"""

import asyncio
import discord
from discord.ext import commands

from config import TOKEN, PREFIX, logger


# ─────────────────────────────────────────────────────────────────────────
# EXTENSIONS CẦN LOAD — thêm đường dẫn module vào đây khi có Cog mới
# ─────────────────────────────────────────────────────────────────────────
EXTENSIONS = [
    "cogs.anti",  # Module SAFE-ANTI 2.0 — load qua cogs/anti/__init__.py
]


# ─────────────────────────────────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content  = True
intents.members          = True
intents.guilds           = True
intents.guild_messages   = True
intents.moderation       = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


@bot.event
async def on_ready() -> None:
    logger.info(f"Bot đã sẵn sàng: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Đang phục vụ {len(bot.guilds)} server(s).")

    try:
        synced = await bot.tree.sync()
        logger.info(f"Đã sync {len(synced)} slash command(s) toàn cầu.")
    except Exception as e:
        logger.error(f"Lỗi khi sync slash commands: {e}")


# ─────────────────────────────────────────────────────────────────────────
# LOAD EXTENSIONS
# ─────────────────────────────────────────────────────────────────────────
async def load_extensions() -> None:
    for ext in EXTENSIONS:
        try:
            await bot.load_extension(ext)
            logger.info(f"Đã load extension: {ext}")
        except Exception as e:
            logger.error(f"Lỗi khi load extension '{ext}': {e}")


# ─────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────
async def main() -> None:
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
