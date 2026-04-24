"""Infrastructure Tools - LangChain @tool 实现

提供 Agent 可用的工具实现。
作为 Infrastructure 层组件，直接调用其他 Infrastructure Adapter。

工具列表：
- search_questions: 向量检索题目（Embedding + Qdrant + Rerank）
- search_web: Web 搜索（调用 WebSearchAdapter）
- get_company_hot_topics: 公司热门考点查询（Neo4j）
- get_knowledge_relations: 知识点关联查询（Neo4j）
- get_cross_company_trends: 跨公司考点趋势查询（Neo4j）
- load_memory_reference: 加载记忆详情
- search_session_history: 语义检索历史
- load_skill: 加载用户 Skill
- update_preferences: 更新用户偏好
- update_behaviors: 更新用户行为模式
"""

from app.infrastructure.tools.search_questions import search_questions
from app.infrastructure.tools.search_web import search_web
from app.infrastructure.tools.get_company_hot_topics import get_company_hot_topics
from app.infrastructure.tools.get_knowledge_relations import get_knowledge_relations
from app.infrastructure.tools.get_cross_company_trends import get_cross_company_trends
from app.infrastructure.tools.memory_tools import (
    load_memory_reference,
    search_session_history,
    load_skill,
    update_preferences,
    update_behaviors,
    get_memory_tools,
)

__all__ = [
    "search_questions",
    "search_web",
    "get_company_hot_topics",
    "get_knowledge_relations",
    "get_cross_company_trends",
    "load_memory_reference",
    "search_session_history",
    "load_skill",
    "update_preferences",
    "update_behaviors",
    "get_memory_tools",
]