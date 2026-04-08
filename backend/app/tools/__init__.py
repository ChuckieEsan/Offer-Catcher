"""智能体工具箱

提供 Embedding、Web 搜索、记忆读写等工具，供 Pipeline 和 Agents 使用。
"""

from app.tools.embedding_tool import EmbeddingTool, get_embedding_tool
from app.tools.web_search_tool import WebSearchTool, get_web_search_tool, WebSearchResult
from app.tools.memory_tools import (
    save_user_preferences,
    save_user_profile,
    update_learning_progress,
    get_user_preferences,
    get_user_profile,
    get_learning_progress,
    clear_user_memory,
    AgentContext,
)

__all__ = [
    # Embedding
    "EmbeddingTool",
    "get_embedding_tool",
    # Web Search
    "WebSearchTool",
    "get_web_search_tool",
    "WebSearchResult",
    # Memory Tools
    "save_user_preferences",
    "save_user_profile",
    "update_learning_progress",
    "get_user_preferences",
    "get_user_profile",
    "get_learning_progress",
    "clear_user_memory",
    "AgentContext",
]