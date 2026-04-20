"""Infrastructure Memory Persistence Module

记忆持久化模块，提供：
- 记忆仓库（MEMORY.md + references）
- 会话摘要仓库（session_summaries）
- 检索服务（异步检索 + checkpoint 更新）
- 检索锁（并发控制）
"""

from app.infrastructure.persistence.memory.memory_retrieval import (
    # Lock functions
    get_retrieval_lock_key,
    acquire_retrieval_lock,
    release_retrieval_lock,
    is_retrieval_in_progress,
    # Retrieval functions
    retrieve_and_update_checkpoint,
    merge_memory_context,
    format_session_summary,
    trigger_retrieval,
)

__all__ = [
    # Lock
    "get_retrieval_lock_key",
    "acquire_retrieval_lock",
    "release_retrieval_lock",
    "is_retrieval_in_progress",
    # Retrieval
    "retrieve_and_update_checkpoint",
    "merge_memory_context",
    "format_session_summary",
    "trigger_retrieval",
]