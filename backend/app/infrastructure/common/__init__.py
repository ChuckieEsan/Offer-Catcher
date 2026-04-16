"""基础设施层通用工具

包含日志、异常、缓存等通用组件。
"""

from app.infrastructure.common.logger import logger, setup_logger

__all__ = [
    "logger",
    "setup_logger",
]