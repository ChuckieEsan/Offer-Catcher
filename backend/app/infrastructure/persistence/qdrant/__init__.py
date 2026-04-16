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

__all__ = [
    "QdrantClient",
    "get_qdrant_client",
    "QdrantQuestionRepository",
    "get_question_repository",
]