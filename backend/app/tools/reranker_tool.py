"""重排工具模块

封装 RerankerAdapter，对检索结果进行精排。
底层服务由 infrastructure/adapters 提供。
"""

from app.infrastructure.adapters.reranker_adapter import (
    RerankerAdapter,
    get_reranker_adapter,
)
from app.infrastructure.common.logger import logger


class RerankerTool:
    """重排工具

    封装 RerankerAdapter，对检索候选结果进行精排。
    底层服务由 Adapter 提供。
    """

    def __init__(self) -> None:
        """初始化 Reranker 工具

        使用 RerankerAdapter 作为底层服务。
        """
        self._adapter = get_reranker_adapter()
        logger.info("RerankerTool initialized with RerankerAdapter")

    @property
    def adapter(self) -> RerankerAdapter:
        """获取底层 Adapter 实例"""
        return self._adapter

    def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        """对候选文本进行重排

        Args:
            query: 查询文本
            candidates: 候选文本列表
            top_k: 返回前 k 个结果

        Returns:
            [(原始索引, 重排分数)] 列表，按分数降序排列
        """
        return self._adapter.rerank(query, candidates, top_k)

    def rerank_with_scores(
        self,
        query: str,
        candidates: list[str],
    ) -> list[float]:
        """返回所有候选的重排分数（不排序）

        Args:
            query: 查询文本
            candidates: 候选文本列表

        Returns:
            重排分数列表（与 candidates 顺序一致）
        """
        return self._adapter.compute_scores(query, candidates)


# 单例获取函数
_reranker_tool: "RerankerTool | None" = None


def get_reranker_tool() -> RerankerTool:
    """获取 Reranker 工具单例

    Returns:
        RerankerTool 实例
    """
    global _reranker_tool
    if _reranker_tool is None:
        _reranker_tool = RerankerTool()
    return _reranker_tool


__all__ = ["RerankerTool", "get_reranker_tool"]