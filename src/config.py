"""
config.py — Cấu hình toàn cục cho Discord Bot
Chứa: Token, Prefix, Logging setup gốc, và các biến môi trường.

Lưu ý: File này KHÔNG chứa hằng số nghiệp vụ của từng module.
Các hằng số riêng của module Anti nằm trong cogs/anti/constants.py.
"""

import os
import logging

# ─────────────────────────────────────────────────────────────────────────
# BOT CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────
TOKEN  = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PREFIX = os.getenv("DISCORD_BOT_PREFIX", "!")

# ─────────────────────────────────────────────────────────────────────────
# LOGGING SETUP GỐC — dùng chung cho toàn bộ dự án
# ─────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("DiscordBot")
