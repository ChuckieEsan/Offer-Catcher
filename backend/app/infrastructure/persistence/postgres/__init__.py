"""PostgreSQL 持久化模块

提供 PostgreSQL 客户端、LangGraph Checkpointer 和仓库实现。
"""

from app.infrastructure.persistence.postgres.client import (
    PostgresClient,
    get_postgres_client,
)
from app.infrastructure.persistence.postgres.checkpointer import (
    get_checkpointer,
    init_checkpointer,
)
from app.infrastructure.persistence.postgres.extract_task_repository import (
    PostgresExtractTaskRepository,
    get_extract_task_repository,
)
from app.infrastructure.persistence.postgres.interview_session_repository import (
    PostgresInterviewSessionRepository,
    get_interview_session_repository,
)
from app.infrastructure.persistence.postgres.conversation_repository import (
    PostgresConversationRepository,
    get_conversation_repository,
)
from app.infrastructure.persistence.postgres.favorite_repository import (
    PostgresFavoriteRepository,
    get_favorite_repository,
)
from app.infrastructure.persistence.postgres.memory_repository import (
    PostgresMemoryRepository,
    get_memory_repository,
)
from app.infrastructure.persistence.postgres.session_summary_repository import (
    PostgresSessionSummaryRepository,
    get_session_summary_repository,
)

__all__ = [
    "PostgresClient",
    "get_postgres_client",
    "get_checkpointer",
    "init_checkpointer",
    "PostgresExtractTaskRepository",
    "get_extract_task_repository",
    "PostgresInterviewSessionRepository",
    "get_interview_session_repository",
    "PostgresConversationRepository",
    "get_conversation_repository",
    "PostgresFavoriteRepository",
    "get_favorite_repository",
    # Memory Repository
    "PostgresMemoryRepository",
    "get_memory_repository",
    # Session Summary Repository
    "PostgresSessionSummaryRepository",
    "get_session_summary_repository",
]