"""Application Agents Memory Module

记忆 Agent 模块，提供：
- 记忆 Agent（后台提取）
- 记忆 Tools（Agent 工具）
- 游标管理（Redis）
- Stop Hook（对话结束触发）
- 检索服务（从 Infrastructure 层导入）

注：检索锁和检索 Worker 已移至 Infrastructure 层（DDD 原则）
"""

from app.application.agents.memory.agent import (
    create_memory_agent,
    run_memory_agent,
    MEMORY_AGENT_TOOLS,
)
from app.application.agents.memory.tools import (
    write_session_summary,
    update_preferences,
    update_behaviors,
    update_memory_index,
    update_cursor,
)
from app.application.agents.memory.cursor import (
    get_cursor_key,
    save_cursor,
    get_cursor,
    has_memory_writes_since,
    get_messages_since_cursor,
)
from app.application.agents.memory.hooks import (
    extract_memories,
    create_memory_extraction_hook,
    safe_extract_memories,
)
# 从 Infrastructure 层导入检索服务（DDD 依赖倒置）
from app.infrastructure.persistence.memory import (
    get_retrieval_lock_key,
    acquire_retrieval_lock,
    release_retrieval_lock,
    is_retrieval_in_progress,
    retrieve_and_update_checkpoint,
    merge_memory_context,
    format_session_summary,
    trigger_retrieval,
)

__all__ = [
    # Agent
    "create_memory_agent",
    "run_memory_agent",
    "MEMORY_AGENT_TOOLS",
    # Tools
    "write_session_summary",
    "update_preferences",
    "update_behaviors",
    "update_memory_index",
    "update_cursor",
    # Cursor
    "get_cursor_key",
    "save_cursor",
    "get_cursor",
    "has_memory_writes_since",
    "get_messages_since_cursor",
    # Hooks
    "extract_memories",
    "create_memory_extraction_hook",
    "safe_extract_memories",
    # Retrieval (from Infrastructure)
    "get_retrieval_lock_key",
    "acquire_retrieval_lock",
    "release_retrieval_lock",
    "is_retrieval_in_progress",
    "retrieve_and_update_checkpoint",
    "merge_memory_context",
    "format_session_summary",
    "trigger_retrieval",
]