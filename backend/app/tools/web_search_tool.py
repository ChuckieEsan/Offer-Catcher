"""Web 搜索工具模块

封装 WebSearchAdapter，为 Agent 提供联网搜索能力。
底层服务由 infrastructure/adapters 提供。

包含：
- WebSearchTool：封装 WebSearchAdapter 的工具类
- search_web：LangChain @tool 装饰器函数（供 Agent 调用）
"""

from app.infrastructure.adapters.web_search_adapter import (
    WebSearchAdapter,
    WebSearchResult,
    get_web_search_adapter,
)
from app.infrastructure.common.logger import logger


class WebSearchTool:
    """Web 搜索工具

    封装 WebSearchAdapter，提供联网搜索能力。
    底层服务由 Adapter 提供。
    """

    def __init__(self, max_results: int = 5) -> None:
        """初始化 Web 搜索工具

        Args:
            max_results: 最大返回结果数，默认 5
        """
        self._adapter = get_web_search_adapter()
        self._max_results = max_results
        logger.info(f"WebSearchTool initialized, max_results={max_results}")

    @property
    def adapter(self) -> WebSearchAdapter:
        """获取底层 Adapter 实例"""
        return self._adapter

    def search(
        self,
        query: str,
        max_results: int | None = None,
    ) -> list[WebSearchResult]:
        """搜索网页

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            搜索结果列表
        """
        return self._adapter.search(query, max_results or self._max_results)

    def search_for_answer(
        self,
        question: str,
        company: str,
        position: str,
    ) -> str:
        """搜索题目相关资料

        Args:
            question: 题目文本
            company: 公司名称
            position: 岗位名称

        Returns:
            格式化后的搜索结果
        """
        return self._adapter.search_for_context(question, company, position)


# 单例获取函数
_web_search_tool: "WebSearchTool | None" = None


def get_web_search_tool(max_results: int = 5) -> WebSearchTool:
    """获取 Web 搜索工具单例

    Args:
        max_results: 最大返回结果数（首次调用时生效）

    Returns:
        WebSearchTool 实例
    """
    global _web_search_tool
    if _web_search_tool is None:
        _web_search_tool = WebSearchTool(max_results=max_results)
    return _web_search_tool


__all__ = [
    "WebSearchResult",
    "WebSearchTool",
    "get_web_search_tool",
]


# ==================== LangChain @tool 装饰器函数 ====================

from langchain_core.tools import tool
from app.utils.telemetry import traced
from app.application.services.cache_service import get_cache_service, CacheKeys


def _do_web_search(query: str, max_results: int) -> str:
    """执行实际的 Web 搜索（内部函数）"""
    try:
        web_tool = get_web_search_tool(max_results=max_results)
        results = web_tool.search(query)

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
@traced
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