"""知识点关联查询工具

获取某知识点的关联知识点，帮助用户系统化学习。
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys
from app.infrastructure.observability import traced


@tool
@traced()
def get_knowledge_relations(entity: str, limit: int = 5) -> str:
    """获取某知识点的关联知识点

    分析知识点之间的共现关系，帮助用户了解学习路径。
    例如：查询 "RAG" 可能返回 "向量数据库"、"Embedding"、"LLM 幻觉" 等。

    Args:
        entity: 知识点名称（如"RAG"、"LangChain"、"Redis"、"微服务"）
        limit: 返回数量，默认 5

    Returns:
        与该知识点常一起考察的其他知识点列表
    """
    from app.infrastructure.persistence.neo4j import get_graph_client
    from app.domain.question.repositories import GraphRepository
    from app.application.services.cache_service import get_cache_service

    graph_repo: GraphRepository = get_graph_client()
    cache = get_cache_service()

    # 构建缓存 key
    cache_key = CacheKeys.tool_knowledge_relations(entity)

    def fetch() -> str:
        try:
            related = graph_repo.get_related_entities(entity, limit=limit)

            if not related:
                return f"暂无 '{entity}' 的关联知识点数据。\n可能该知识点尚未被录入，或 Neo4j 数据未初始化。"

            output = [f"**与 '{entity}' 常一起考察的知识点:**\n"]
            for e in related:
                related_entity = e.get("related_entity", "")
                count = e.get("co_occurrence_count", 0)
                output.append(f"- **{related_entity}** (共现次数: {count})")

            output.append(f"\n💡 建议在学习 '{entity}' 后，继续深入以上关联知识点。")
            return "\n".join(output)

        except Exception as e:
            logger.error(f"get_knowledge_relations failed: {e}")
            return f"查询失败: {e}"

    # 使用缓存（图数据变化不频繁，缓存 10 分钟）
    return cache.get_with_lock(cache_key, fetch, ttl=600)


__all__ = ["get_knowledge_relations"]