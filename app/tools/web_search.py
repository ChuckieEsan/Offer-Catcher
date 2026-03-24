"""Web 搜索工具模块

为异步 Worker 提供联网搜索能力，使用 DuckDuckGo 搜索最新资料。
"""

from typing import Optional
from pydantic import BaseModel, Field

from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_core.tools import BaseTool  # noqa: F401

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

    使用 DuckDuckGo 搜索网页，为异步 Worker 提供联网搜索能力。
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
        self._tool: Optional[DuckDuckGoSearchRun] = None
        logger.info(f"Web search tool initialized, max_results={max_results}")

    @property
    def tool(self) -> DuckDuckGoSearchRun:
        """获取 DuckDuckGo 工具实例（延迟加载）"""
        if self._tool is None:
            self._tool = DuckDuckGoSearchRun()
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
            # 使用 DuckDuckGo 搜索
            results = self.tool.invoke(query)
            logger.debug(f"Search query: {query}, raw results: {results}")

            # 解析结果
            parsed_results = self._parse_results(results, max_results)

            logger.info(
                f"Web search completed: query='{query}', results={len(parsed_results)}"
            )
            return parsed_results

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            raise

    def _parse_results(
        self,
        raw_results: str,
        max_results: int,
    ) -> list[WebSearchResult]:
        """解析搜索结果

        DuckDuckGo 返回的结果格式需要解析。
        结果通常以 "Title | URL | Description" 的格式返回。

        Args:
            raw_results: 原始搜索结果
            max_results: 最大结果数

        Returns:
            解析后的结果列表
        """
        if not raw_results:
            return []

        results = []
        lines = raw_results.strip().split("\n")

        for line in lines[:max_results]:
            # 尝试解析每一行
            # 格式：Title | URL | Description
            parts = line.split("|")
            if len(parts) >= 3:
                title = parts[0].strip()
                url = parts[1].strip()
                content = parts[2].strip()
                results.append(
                    WebSearchResult(
                        title=title,
                        url=url,
                        content=content,
                    )
                )
            elif len(parts) == 2:
                # 只有标题和 URL
                title = parts[0].strip()
                url = parts[1].strip()
                results.append(
                    WebSearchResult(
                        title=title,
                        url=url,
                        content="",
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