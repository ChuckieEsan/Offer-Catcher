"""Web 搜索适配器

封装 Tavily 搜索 API，提供联网搜索能力。
作为基础设施层适配器，为应用层和领域层提供搜索服务。
"""

from typing import Optional
from pydantic import BaseModel, Field

from langchain_tavily import TavilySearch

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class WebSearchResult(BaseModel):
    """Web 搜索结果

    Attributes:
        title: 结果标题
        url: 结果链接
        content: 结果内容摘要
    """

    title: str = Field(description="结果标题")
    url: str = Field(description="结果链接")
    content: str = Field(default="", description="结果内容摘要")


class WebSearchAdapter:
    """Web 搜索适配器

    封装 Tavily 搜索 API，提供联网搜索能力。
    用于异步 Worker 或应用服务搜索最新资料。

    设计原则：
    - 复用 LangChain TavilySearch 组件
    - 支持依赖注入（便于测试）
    - 结构化返回结果
    """

    def __init__(
        self,
        max_results: int = 5,
    ) -> None:
        """初始化 Web 搜索适配器

        Args:
            max_results: 最大返回结果数，默认 5
        """
        self._max_results = max_results

        settings = get_settings()
        self._tool = TavilySearch(
            max_results=self._max_results,
            tavily_api_key=settings.tavily_api_key,
        )

        logger.info(f"WebSearchAdapter initialized, max_results={max_results}")

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> list[WebSearchResult]:
        """搜索网页

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数，默认使用初始化时的值

        Returns:
            搜索结果列表
        """
        max_results = max_results or self._max_results

        try:
            raw_results = self._tool.invoke(query)
            logger.debug(f"Search query: {query}, raw results: {raw_results}")

            parsed_results = self._parse_results(raw_results, max_results)

            logger.info(
                f"Web search completed: query='{query}', results={len(parsed_results)}"
            )
            return parsed_results

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            raise

    def _parse_results(
        self,
        raw_results,
        max_results: int,
    ) -> list[WebSearchResult]:
        """解析搜索结果

        Args:
            raw_results: 原始搜索结果
            max_results: 最大结果数

        Returns:
            解析后的结果列表
        """
        if not raw_results:
            return []

        items = raw_results.get("results", []) if isinstance(raw_results, dict) else raw_results

        results = []
        for item in items[:max_results]:
            if isinstance(item, dict):
                results.append(
                    WebSearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                    )
                )

        return results

    def search_for_context(
        self,
        question: str,
        company: str = "",
        position: str = "",
    ) -> str:
        """搜索题目相关资料，返回格式化文本

        Args:
            question: 题目文本
            company: 公司名称
            position: 岗位名称

        Returns:
            格式化后的搜索结果（可用于 LLM 生成答案）
        """
        search_query = f"{question} {company} {position}"

        results = self.search(search_query)

        if not results:
            return "未找到相关资料"

        formatted = "以下是搜索到的相关资料：\n\n"
        for i, r in enumerate(results, 1):
            formatted += f"{i}. {r.title}\n"
            formatted += f"   来源：{r.url}\n"
            if r.content:
                formatted += f"   摘要：{r.content}\n"
            formatted += "\n"

        return formatted


# 单例获取函数
_web_search_adapter: Optional[WebSearchAdapter] = None


def get_web_search_adapter() -> WebSearchAdapter:
    """获取 Web 搜索适配器单例

    Returns:
        WebSearchAdapter 实例
    """
    global _web_search_adapter
    if _web_search_adapter is None:
        _web_search_adapter = WebSearchAdapter()
    return _web_search_adapter


__all__ = [
    "WebSearchResult",
    "WebSearchAdapter",
    "get_web_search_adapter",
]