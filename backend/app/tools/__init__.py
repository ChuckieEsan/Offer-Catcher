"""智能体工具箱

提供 Embedding、Web 搜索、Rerank、记忆读写等工具，供 Pipeline 和 Agents 使用。
"""

from app.tools.embedding_tool import EmbeddingTool, get_embedding_tool
from app.tools.reranker_tool import RerankerTool, get_reranker_tool
from app.tools.web_search_tool import WebSearchTool, get_web_search_tool, WebSearchResult
from app.tools.memory_tools import (
    get_user_memory,
    save_user_preferences,
    save_user_profile,
    update_learning_progress,
    clear_user_memory,
    UserContext,
)

__all__ = [
    # Embedding
    "EmbeddingTool",
    "get_embedding_tool",
    # Reranker
    "RerankerTool",
    "get_reranker_tool",
    # Web Search
    "WebSearchTool",
    "get_web_search_tool",
    "WebSearchResult",
    # Memory Tools
    "get_user_memory",
    "save_user_preferences",
    "save_user_profile",
    "update_learning_progress",
    "clear_user_memory",
    "UserContext",
]