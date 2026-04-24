"""跨公司考点趋势查询工具

获取跨多家公司考察的热门考点，帮助用户了解行业趋势。
"""

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys
from app.infrastructure.observability import traced


@tool
@traced()
def get_cross_company_trends(min_companies: int = 2, limit: int = 20) -> str:
    """获取跨多家公司考察的热门考点

    分析行业高频考点，帮助用户了解行业趋势和重点。

    Args:
        min_companies: 最少被多少家公司考察过，默认 2
        limit: 返回数量，默认 20

    Returns:
        跨公司考点列表，包含考点名称、考察公司列表、总次数
    """
    from app.infrastructure.persistence.neo4j import get_graph_client
    from app.domain.question.repositories import GraphRepository
    from app.application.services.cache_service import get_cache_service

    graph_repo: GraphRepository = get_graph_client()
    cache = get_cache_service()

    # 构建缓存 key
    cache_key = CacheKeys.tool_cross_company_trends(min_companies)

    def fetch() -> str:
        try:
            cross_entities = graph_repo.get_cross_company_entities(min_companies=min_companies)

            if not cross_entities:
                return f"暂无跨 {min_companies}+ 家公司的考点数据。\n可能题库数据不足，或 Neo4j 数据未初始化。"

            # 按总次数排序，取前 limit 个
            sorted_entities = sorted(cross_entities, key=lambda x: x.get('total_count', 0), reverse=True)[:limit]

            output = [f"**跨 {min_companies}+ 家公司的热门考点:**\n"]
            for e in sorted_entities:
                entity = e.get("entity", "")
                companies = e.get("companies", [])
                total_count = e.get("total_count", 0)

                # 格式化公司列表（只显示前5家）
                companies_str = ", ".join(companies[:5])
                if len(companies) > 5:
                    companies_str += f" 等{len(companies)}家"

                output.append(f"- **{entity}**: {companies_str} (共 {total_count} 次)")

            output.append(f"\n💡 以上考点是行业高频热点，建议优先准备。")
            return "\n".join(output)

        except Exception as e:
            logger.error(f"get_cross_company_trends failed: {e}")
            return f"查询失败: {e}"

    # 使用缓存（图数据变化不频繁，缓存 10 分钟）
    return cache.get_with_lock(cache_key, fetch, ttl=600)


__all__ = ["get_cross_company_trends"]