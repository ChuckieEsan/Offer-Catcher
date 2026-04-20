"""Application Memory Module

记忆应用层模块，提供：
- 记忆 Agent
- 记忆 Tools
- 游标管理
- Stop Hook
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
]