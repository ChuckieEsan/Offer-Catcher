"""图数据库查询 LangChain @tool

作为 Infrastructure 层组件，直接调用 GraphClient。
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys
from app.infrastructure.observability import traced


def _do_query_graph(question: str) -> str:
    """执行实际的图数据库查询（内部函数）"""
    from app.infrastructure.persistence.neo4j import get_graph_client

    try:
        graph_client = get_graph_client()

        # 提取关键词
        keywords = question.replace("关系", "").replace("?", "").replace("知识", "").split()

        # 如果有关键词，查询相关知识点
        if keywords and keywords[0]:
            keyword = keywords[0]
            # 使用 get_related_entities 获取相关知识点
            related = graph_client.get_related_entities(keyword, limit=5)

            if not related:
                # 如果没有相关知识点，尝试获取热门考点
                top_entities = graph_client.get_top_entities(limit=5)
                if not top_entities:
                    return "图数据库中暂无知识点数据"

                output = ["热门考点:"]
                for e in top_entities:
                    output.append(f"- {e.get('entity', e)}")
                return "\n".join(output)

            output = [f"与 '{keyword}' 相关的知识点:"]
            for e in related:
                output.append(f"- {e.get('related_entity', e.get('entity', e))}")
                count = e.get('co_occurrence_count', '')
                if count:
                    output.append(f"  共现次数: {count}")
            return "\n".join(output)
        else:
            # 没有关键词时，返回热门考点
            top_entities = graph_client.get_top_entities(limit=10)
            if not top_entities:
                return "图数据库中暂无知识点数据"

            output = ["热门考点 Top 10:"]
            for i, e in enumerate(top_entities, 1):
                entity = e.get('entity', e)
                count = e.get('count', '')
                output.append(f"{i}. {entity}" + (f" (考察次数: {count})" if count else ""))
            return "\n".join(output)

    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return f"图数据库查询失败: {e}"


@tool
@traced
def query_graph(question: str) -> str:
    """查询图数据库，获取知识点之间的关系

    结果会被缓存 10 分钟。

    Args:
        question: 查询问题

    Returns:
        查询结果
    """
    # Lazy import 避免 circular import
    from app.application.services.cache_service import get_cache_service

    cache = get_cache_service()

    # 构建缓存 key
    query_hash = CacheKeys.hash_params(question)
    cache_key = CacheKeys.tool_query_graph(query_hash)

    # 使用缓存服务（图数据变化不频繁，缓存 10 分钟）
    return cache.get_with_lock(
        cache_key,
        lambda: _do_query_graph(question),
        ttl=600,
    )


__all__ = ["query_graph"]