"""Tool Ports - 工具接口定义

定义 Agent 可用工具的 Protocol 接口。
作为 Application 层组件，不包含实现细节。

Port 定义：
- SearchQuestionsPort: 搜索本地题库
- SearchWebPort: Web 搜索
- QueryGraphPort: 图数据库查询

实际实现在 Infrastructure 层：
- infrastructure/tools/search_questions.py
- infrastructure/tools/search_web.py
- infrastructure/tools/query_graph.py

通过 Factory 组装时注入实现。
"""

from typing import Protocol


class SearchQuestionsPort(Protocol):
    """搜索题目工具接口

    搜索本地向量数据库中的面试题目。
    采用两阶段检索：向量召回 + Rerank 精排。
    """

    def __call__(
        self,
        query: str,
        company: str = None,
        position: str = None,
        k: int = 5,
    ) -> str:
        """执行搜索

        Args:
            query: 搜索关键词
            company: 公司名称（可选，用于语义增强）
            position: 岗位名称（可选，用于语义增强）
            k: 返回数量，默认 5

        Returns:
            搜索结果，以文本形式返回
        """
        ...


class SearchWebPort(Protocol):
    """Web 搜索工具接口

    联网搜索获取最新信息。
    仅在用户明确要求或本地题库无结果时使用。
    """

    def __call__(
        self,
        query: str,
        max_results: int = 3,
    ) -> str:
        """执行 Web 搜索

        Args:
            query: 搜索关键词
            max_results: 最大结果数，默认 3

        Returns:
            搜索结果，以文本形式返回
        """
        ...


class QueryGraphPort(Protocol):
    """图数据库查询工具接口

    查询图数据库，获取知识点之间的关系。
    """

    def __call__(
        self,
        question: str,
    ) -> str:
        """执行图数据库查询

        Args:
            question: 查询问题

        Returns:
            查询结果
        """
        ...


__all__ = [
    "SearchQuestionsPort",
    "SearchWebPort",
    "QueryGraphPort",
]