"""通用缓存工具模块

底层服务由 infrastructure/common/cache 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.infrastructure.common.cache import cached, singleton

__all__ = ["cached", "singleton"]