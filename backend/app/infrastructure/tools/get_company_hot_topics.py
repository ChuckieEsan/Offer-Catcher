"""公司热门考点查询工具

获取某公司/岗位的高频考点，帮助用户针对性准备面试。
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys
from app.infrastructure.observability import traced


@tool
@traced()
def get_company_hot_topics(company: str, limit: int = 10) -> str:
    """获取某公司的高频考点

    用于分析某公司的面试重点，帮助用户针对性准备。

    Args:
        company: 公司名称（如"字节跳动"、"阿里"、"腾讯"）
        limit: 返回数量，默认 10

    Returns:
        高频考点列表，包含考点名称和考察次数
    """
    from app.infrastructure.persistence.neo4j import get_graph_client
    from app.domain.question.repositories import GraphRepository
    from app.application.services.cache_service import get_cache_service

    graph_repo: GraphRepository = get_graph_client()
    cache = get_cache_service()

    # 构建缓存 key
    cache_key = CacheKeys.tool_company_topics(company)

    def fetch() -> str:
        try:
            top_entities = graph_repo.get_top_entities(company=company, limit=limit)

            if not top_entities:
                return f"暂无 {company} 的考点数据。可能该公司尚未录入题库，或 Neo4j 数据未初始化。"

            output = [f"**{company} 高频考点 Top {len(top_entities)}:**\n"]
            for i, e in enumerate(top_entities, 1):
                entity = e.get("entity", "")
                count = e.get("count", 0)
                output.append(f"{i}. **{entity}** (考察次数: {count})")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"get_company_hot_topics failed: {e}")
            return f"查询失败: {e}"

    # 使用缓存（图数据变化不频繁，缓存 10 分钟）
    return cache.get_with_lock(cache_key, fetch, ttl=600)


__all__ = ["get_company_hot_topics"]