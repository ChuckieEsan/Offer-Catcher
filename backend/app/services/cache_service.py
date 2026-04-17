"""缓存服务（向后兼容导入转发）

服务已拆分：
- CacheAdapter: infrastructure/adapters/cache_adapter.py（基础技术能力）
- CacheApplicationService: application/services/cache_service.py（业务编排）

此模块仅提供向后兼容的导入。
"""

from app.application.services.cache_service import (
    CacheKeys,
    CacheApplicationService,
    get_cache_service,
)

# 向后兼容别名
CacheService = CacheApplicationService

__all__ = [
    "CacheKeys",
    "CacheService",
    "CacheApplicationService",
    "get_cache_service",
]