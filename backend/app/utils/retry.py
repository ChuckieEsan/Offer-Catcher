"""重试装饰器模块

底层服务由 infrastructure/common/retry 提供。
此模块仅提供向后兼容的导入转发。
"""

from app.infrastructure.common.retry import retry

__all__ = ["retry"]