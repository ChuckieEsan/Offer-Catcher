"""智能体工具箱

提供 Embedding、Web 搜索等工具，供 Pipeline 和 Agents 使用。

注意：向量检索功能已移至 app.db.qdrant_client.QdrantManager
"""

from app.tools.embedding import EmbeddingTool, get_embedding_tool
from app.tools.web_search import WebSearchTool, get_web_search_tool, WebSearchResult

__all__ = [
    "EmbeddingTool",
    "get_embedding_tool",
    "WebSearchTool",
    "get_web_search_tool",
    "WebSearchResult",
]