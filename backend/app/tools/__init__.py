"""智能体工具箱（兼容层）

提供 LangChain @tool 的兼容导入。
实际工具已迁移到 application/agents/ 目录。

注意：
- EmbeddingTool、RerankerTool、WebSearchTool 已删除
- 请直接使用对应的 Adapter：
  - get_embedding_adapter()
  - get_reranker_adapter()
  - get_web_search_adapter()
"""

# LangChain @tool 装饰器函数（兼容导入）
from app.application.agents.shared.tools.search_web import search_web
from app.application.agents.shared.tools.search_questions import search_questions
from app.application.agents.shared.tools.query_graph import query_graph

# UserContext 保留
from app.tools.context import UserContext

__all__ = [
    # LangChain @tool 函数
    "search_web",
    "search_questions",
    "query_graph",
    # Context
    "UserContext",
]