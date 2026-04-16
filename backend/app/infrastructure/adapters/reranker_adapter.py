"""重排适配器

封装 CrossEncoder (BGE-Reranker)，对检索结果进行精排。
作为基础设施层适配器，为应用层和领域层提供重排能力。
"""

import os
from typing import Optional

from sentence_transformers import CrossEncoder

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class RerankerAdapter:
    """重排适配器

    封装 CrossEncoder，对检索候选结果进行精排。
    支持 query-doc pairs 的相关性打分。

    设计原则：
    - 复用 CrossEncoder 组件
    - 支持依赖注入（便于测试）
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        max_length: int = 512,
        device: str = "cuda",
    ) -> None:
        """初始化 Reranker 适配器

        Args:
            model_path: 模型路径，默认使用配置中的路径
            max_length: 最大序列长度
            device: 运行设备（cuda/cpu）
        """
        settings = get_settings()
        self._model_path = model_path or settings.reranker_model_path
        self._max_length = max_length
        self._device = device

        if not os.path.exists(self._model_path):
            raise FileNotFoundError(f"Reranker model not found at: {self._model_path}")

        self._reranker = CrossEncoder(
            self._model_path,
            max_length=self._max_length,
            device=self._device,
        )

        logger.info(
            f"RerankerAdapter initialized: model={self._model_path}, "
            f"max_length={max_length}, device={device}"
        )

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
            pairs = [[query, doc] for doc in candidates]
            scores = self._reranker.predict(pairs)
            indexed_scores = list(enumerate(scores))
            ranked = sorted(indexed_scores, key=lambda x: x[1], reverse=True)[:top_k]

            logger.info(f"Reranked {len(candidates)} candidates, returning top {top_k}")
            return ranked

        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            raise

    def compute_scores(
        self,
        query: str,
        candidates: list[str],
    ) -> list[float]:
        """计算所有候选的重排分数

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
            logger.error(f"Compute scores failed: {e}")
            raise


# 单例获取函数
_reranker_adapter: Optional[RerankerAdapter] = None


def get_reranker_adapter() -> RerankerAdapter:
    """获取 Reranker 适配器单例

    Returns:
        RerankerAdapter 实例
    """
    global _reranker_adapter
    if _reranker_adapter is None:
        _reranker_adapter = RerankerAdapter()
    return _reranker_adapter


__all__ = [
    "RerankerAdapter",
    "get_reranker_adapter",
]