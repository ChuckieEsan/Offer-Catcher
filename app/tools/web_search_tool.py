"""Web 搜索工具模块

为异步 Worker 提供联网搜索能力，使用 Tavily 搜索最新资料。
"""

from typing import Optional
from pydantic import BaseModel, Field

from langchain_tavily import TavilySearch
from langchain_core.tools import BaseTool  # noqa: F401

from app.config.settings import get_settings
from app.utils.logger import logger


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


class WebSearchTool:
    """Web 搜索工具

    使用 Tavily 搜索网页，为异步 Worker 提供联网搜索能力。
    用于在生成答案时搜索最新资料。

    核心功能：
    - 搜索网页获取最新信息
    - 返回结构化的搜索结果
    """

    def __init__(
        self,
        max_results: int = 5,
    ) -> None:
        """初始化 Web 搜索工具

        Args:
            max_results: 最大返回结果数，默认 5
        """
        self.max_results = max_results
        self._tool: Optional[TavilySearch] = None
        logger.info(f"Web search tool initialized, max_results={max_results}")

    @property
    def tool(self) -> TavilySearch:
        """获取 Tavily 工具实例（延迟加载）"""
        if self._tool is None:
            settings = get_settings()
            self._tool = TavilySearch(
                max_results=self.max_results,
                tavily_api_key=settings.tavily_api_key,
            )
        return self._tool

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
        max_results = max_results or self.max_results

        try:
            # 使用 Tavily 搜索
            raw_results = self.tool.invoke(query)
            logger.debug(f"Search query: {query}, raw results: {raw_results}")

            # 解析结果
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

        Tavily 返回 dict，结构为 {'results': [dict(...), ...]}。

        Args:
            raw_results: 原始搜索结果
            max_results: 最大结果数

        Returns:
            解析后的结果列表
        """
        if not raw_results:
            return []

        # Tavily 返回 dict，需要从 results 字段提取列表
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

    def search_for_answer(
        self,
        question: str,
        company: str,
        position: str,
    ) -> str:
        """搜索题目相关资料

        为生成答案搜索相关资料。

        Args:
            question: 题目文本
            company: 公司名称
            position: 岗位名称

        Returns:
            格式化后的搜索结果（可用于 LLM 生成答案）
        """
        # 构造搜索关键词
        search_query = f"{question} {company} {position}"

        results = self.search(search_query)

        if not results:
            return "未找到相关资料"

        # 格式化结果
        formatted = "以下是搜索到的相关资料：\n\n"
        for i, r in enumerate(results, 1):
            formatted += f"{i}. {r.title}\n"
            formatted += f"   来源：{r.url}\n"
            if r.content:
                formatted += f"   摘要：{r.content}\n"
            formatted += "\n"

        return formatted


# 全局单例
_web_search_tool: Optional[WebSearchTool] = None


def get_web_search_tool(max_results: int = 5) -> WebSearchTool:
    """获取 Web 搜索工具单例

    Args:
        max_results: 最大返回结果数

    Returns:
        WebSearchTool 实例
    """
    global _web_search_tool
    if _web_search_tool is None:
        _web_search_tool = WebSearchTool(max_results=max_results)
    return _web_search_tool


# 导出公共 API
__all__ = [
    "WebSearchResult",
    "WebSearchTool",
    "get_web_search_tool",
]


# ==================== LangChain @tool 装饰器函数 ====================

from langchain_core.tools import tool
from app.utils.telemetry import traced


@tool
@traced
def search_web(query: str, max_results: int = 3) -> str:
    """联网搜索获取最新信息（仅在用户明确要求或本地题库无结果时使用）

    注意：这是一个联网搜索工具，会访问互联网。
    默认情况下应优先使用本地题库 search_questions。

    Args:
        query: 搜索关键词
        max_results: 最大结果数，默认 3

    Returns:
        搜索结果，以文本形式返回
    """

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