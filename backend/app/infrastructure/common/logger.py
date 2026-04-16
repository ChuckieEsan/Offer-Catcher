"""基础设施层日志

从应用层日志导入，保持日志统一。
"""

from app.utils.logger import logger, setup_logger

__all__ = ["logger", "setup_logger"]