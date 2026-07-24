"""
utils/logger.py — Custom logging helper dùng chung toàn bot.
Cung cấp hàm get_logger() để tạo logger con theo tên module.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """
    Trả về logger con với tên đã cho.
    Kế thừa cấu hình từ root logger được setup trong config.py.

    Ví dụ:
        from utils.logger import get_logger
        logger = get_logger("AntiCog")
        logger.info("Module khởi động.")
    """
    return logging.getLogger(name)
