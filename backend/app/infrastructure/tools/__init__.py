"""Infrastructure Tools - LangChain @tool 实现

提供 Agent 可用的工具实现。
作为 Infrastructure 层组件，直接调用其他 Infrastructure Adapter。

工具列表：
- search_questions: 向量检索题目（Embedding + Qdrant + Rerank）
- search_web: Web 搜索（调用 WebSearchAdapter）
- query_graph: 图数据库查询（调用 GraphClient）
"""

from app.infrastructure.tools.search_questions import search_questions
from app.infrastructure.tools.search_web import search_web
from app.infrastructure.tools.query_graph import query_graph

__all__ = [
    "search_questions",
    "search_web",
    "query_graph",
]