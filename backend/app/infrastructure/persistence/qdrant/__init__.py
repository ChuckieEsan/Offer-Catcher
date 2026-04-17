"""Qdrant 向量数据库持久化

提供 Qdrant 的客户端和仓库实现。
"""

from app.infrastructure.persistence.qdrant.client import (
    QdrantClient,
    get_qdrant_client,
)
from app.infrastructure.persistence.qdrant.question_repository import (
    QdrantQuestionRepository,
    get_question_repository,
)
from app.infrastructure.persistence.qdrant.cluster_repository import (
    QdrantClusterRepository,
    get_cluster_repository,
)

# 向后兼容的别名
QdrantManager = QdrantClient
get_qdrant_manager = get_qdrant_client

__all__ = [
    "QdrantClient",
    "get_qdrant_client",
    "QdrantManager",
    "get_qdrant_manager",
    "QdrantQuestionRepository",
    "get_question_repository",
    "QdrantClusterRepository",
    "get_cluster_repository",
]