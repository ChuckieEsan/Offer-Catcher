"""重排工具模块

使用 CrossEncoder (BGE-Reranker) 对检索结果进行精排。
"""

import os
from typing import Optional

from sentence_transformers import CrossEncoder

from app.config.settings import get_settings
from app.utils.logger import logger
from app.utils.cache import singleton


class RerankerTool:
    """重排工具

    封装 CrossEncoder，对检索候选结果进行精排。
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        """初始化 Reranker 工具

        Args:
            model_path: 模型路径，默认使用配置中的路径（models/bge-reranker-base）
        """
        settings = get_settings()
        self.model_path = model_path or settings.reranker_model_path

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Reranker model not found at: {self.model_path}")

        # 加载模型
        self._reranker = CrossEncoder(
            self.model_path,
            max_length=512,
            device="cuda"
        )

        logger.info(f"Reranker tool initialized with model: {self.model_path}")

    @property
    def reranker(self) -> CrossEncoder:
        """获取 Reranker 实例"""
        return self._reranker

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
        if not candidates:
            return []

        try:
            # 构建 query-doc pairs
            pairs = [[query, doc] for doc in candidates]

            # 计算重排分数 (CrossEncoder 使用 predict)
            scores = self._reranker.predict(pairs)

            # 构建带索引的结果
            indexed_scores = list(enumerate(scores))

            # 按分数降序排序，取 top_k
            ranked = sorted(indexed_scores, key=lambda x: x[1], reverse=True)[:top_k]

            logger.info(f"Reranked {len(candidates)} candidates, returning top {top_k}")
            return ranked

        except Exception as e:
            logger.error(f"Failed to rerank: {e}")
            raise

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
        if not candidates:
            return []

        try:
            pairs = [[query, doc] for doc in candidates]
            scores = self._reranker.predict(pairs)
            return scores

        except Exception as e:
            logger.error(f"Failed to compute rerank scores: {e}")
            raise


@singleton
def get_reranker_tool() -> RerankerTool:
    """获取 Reranker 工具单例

    Returns:
        RerankerTool 实例
    """
    return RerankerTool()


__all__ = ["RerankerTool", "get_reranker_tool"]