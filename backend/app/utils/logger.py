"""日志工具模块

底层服务由 infrastructure/common/logger 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.infrastructure.common.logger import logger, setup_logger

__all__ = ["logger", "setup_logger"]