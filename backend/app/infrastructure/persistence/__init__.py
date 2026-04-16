"""基础设施层持久化模块

包含各种数据库客户端：
- Qdrant：向量数据库
- PostgreSQL：关系数据库 + LangGraph Checkpointer
- Redis：短期记忆缓存
- Neo4j：图数据库
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

__all__ = [
    # Qdrant
    "QdrantClient",
    "get_qdrant_client",
    # PostgreSQL
    "PostgresClient",
    "get_postgres_client",
    "get_checkpointer",
    "init_checkpointer",
    # Redis
    "RedisClient",
    "get_redis_client",
    # Neo4j
    "Neo4jClient",
    "get_neo4j_client",
    "Neo4jGraphClient",
    "get_graph_client",
]