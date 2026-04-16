"""智能体工具箱

提供 Embedding、Web 搜索、Rerank 等工具，供 Pipeline 和 Agents 使用。

底层服务由 infrastructure/adapters 提供：
- EmbeddingAdapter
- RerankerAdapter
- WebSearchAdapter
- OCRAdapter

记忆相关功能请使用 memory 模块：
    from app.memory import inject_memory_context, trigger_memory_update

Skill 相关功能请使用 skills 模块：
    from app.skills import load_skill
"""

from app.tools.embedding_tool import EmbeddingTool, get_embedding_tool
from app.tools.reranker_tool import RerankerTool, get_reranker_tool
from app.tools.web_search_tool import WebSearchTool, get_web_search_tool
from app.tools.context import UserContext

# LangChain @tool 装饰器函数
from app.tools.web_search_tool import search_web
from app.tools.search_question_tool import search_questions
from app.tools.vision_extractor_tool import extract_interview_questions

# Skill 工具从 skills 模块导入
from app.skills import load_skill

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
    # LangChain @tool functions
    "search_web",
    "search_questions",
    "extract_interview_questions",
    # Skill
    "load_skill",
    "UserContext",
]