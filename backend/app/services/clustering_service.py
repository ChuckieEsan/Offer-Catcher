"""聚类服务（向后兼容导入转发）

服务已迁移到 application/services/clustering_service.py，此模块仅提供向后兼容的导入。
"""

from app.application.services.clustering_service import (
    ClusteringApplicationService,
    ClusteringResult,
    get_clustering_service,
)

# 向后兼容别名
ClusteringService = ClusteringApplicationService

__all__ = [
    "ClusteringService",
    "ClusteringApplicationService",
    "ClusteringResult",
    "get_clustering_service",
]