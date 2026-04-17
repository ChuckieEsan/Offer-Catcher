"""数据库基础设施层

底层服务由 infrastructure/persistence 提供。
"""

from app.infrastructure.persistence.qdrant import (
    QdrantClient,
    get_qdrant_client,
)
from app.infrastructure.persistence.postgres import (
    PostgresClient,
    get_postgres_client,
    get_checkpointer,
    init_checkpointer,
)
from app.infrastructure.persistence.redis import (
    RedisClient,
    get_redis_client,
)
from app.infrastructure.persistence.neo4j import (
    Neo4jClient,
    get_neo4j_client,
    Neo4jGraphClient,
    get_graph_client,
)
from app.models.chat_session import SessionSummary

# 向后兼容的别名
QdrantManager = QdrantClient
get_qdrant_manager = get_qdrant_client

__all__ = [
    "QdrantManager",
    "get_qdrant_manager",
    "PostgresClient",
    "get_postgres_client",
    "SessionSummary",
    "RedisClient",
    "get_redis_client",
    "Neo4jGraphClient",
    "get_graph_client",
    "get_checkpointer",
    "init_checkpointer",
]