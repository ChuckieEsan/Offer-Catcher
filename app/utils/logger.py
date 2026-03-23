"""日志工具模块

提供统一的日志记录配置。
"""

import logging
import sys
from typing import Optional

from app.config.settings import get_settings


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """配置并返回日志记录器

    Args:
        name: 日志记录器名称，默认为 root logger

    Returns:
        配置好的日志记录器
    """
    settings = get_settings()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper()))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台输出
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, settings.log_level.upper()))

    # 格式化
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


# 全局日志单例
logger = setup_logger("offer_catcher")