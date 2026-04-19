"""Web 搜索 LangChain @tool

作为 Infrastructure 层组件，直接调用 WebSearchAdapter。
"""

from langchain_core.tools import tool
from app.infrastructure.common.logger import logger
from app.infrastructure.common.cache_keys import CacheKeys


def _do_web_search(query: str, max_results: int) -> str:
    """执行实际的 Web 搜索（内部函数）"""
    from app.infrastructure.adapters.web_search_adapter import get_web_search_adapter

    try:
        adapter = get_web_search_adapter()
        results = adapter.search(query, max_results)

        if not results:
            return "未找到相关信息"

        output = []
        for r in results:
            output.append(f"标题: {r.title}")
            output.append(f"内容: {r.content[:300]}...")
            output.append("---")

        return "\n".join(output)
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"搜索失败: {e}"


@tool
def search_web(query: str, max_results: int = 3) -> str:
    """联网搜索获取最新信息（仅在用户明确要求或本地题库无结果时使用）

    注意：这是一个联网搜索工具，会访问互联网。
    默认情况下应优先使用本地题库 search_questions。
    结果会被缓存 30 分钟。

    Args:
        query: 搜索关键词
        max_results: 最大结果数，默认 3

    Returns:
        搜索结果，以文本形式返回
    """
    # Lazy import 避免 circular import
    from app.application.services.cache_service import get_cache_service

    cache = get_cache_service()

    # 构建缓存 key
    query_hash = CacheKeys.hash_params(query, max_results=max_results)
    cache_key = CacheKeys.tool_web_search(query_hash)

    # 使用缓存服务（Web 搜索结果缓存 30 分钟）
    return cache.get_with_lock(
        cache_key,
        lambda: _do_web_search(query, max_results),
        ttl=1800,
    )


__all__ = ["search_web"]