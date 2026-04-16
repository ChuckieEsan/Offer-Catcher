"""文本向量化工具模块

封装 EmbeddingAdapter，供 Agent 和 Pipeline 使用。
底层服务由 infrastructure/adapters 提供。
"""

from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.common.logger import logger


class EmbeddingTool:
    """文本向量化工具

    封装 EmbeddingAdapter，提供统一的 embedding 接口。
    支持单条和批量文本向量化，以及上下文拼接后的向量化。

    遵循的设计原则：
    - Context Enrichment：计算向量时拼接上下文 "公司：xxx | 岗位：xxx | 题目：xxx"
    - 底层服务由 Adapter 提供
    """

    def __init__(self) -> None:
        """初始化 Embedding 工具

        使用 EmbeddingAdapter 作为底层服务。
        """
        self._adapter = get_embedding_adapter()
        logger.info("EmbeddingTool initialized with EmbeddingAdapter")

    @property
    def adapter(self) -> EmbeddingAdapter:
        """获取底层 Adapter 实例"""
        return self._adapter

    @property
    def embedding_dimension(self) -> int:
        """获取向量维度"""
        return self._adapter.dimension

    def embed_text(self, text: str) -> list[float]:
        """单条文本向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表
        """
        return self._adapter.embed(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表
        """
        return self._adapter.embed_batch(texts)


# 单例获取函数
_embedding_tool: "EmbeddingTool | None" = None


def get_embedding_tool() -> EmbeddingTool:
    """获取 Embedding 工具单例

    Returns:
        EmbeddingTool 实例
    """
    global _embedding_tool
    if _embedding_tool is None:
        _embedding_tool = EmbeddingTool()
    return _embedding_tool


__all__ = [
    "EmbeddingTool",
    "get_embedding_tool",
]