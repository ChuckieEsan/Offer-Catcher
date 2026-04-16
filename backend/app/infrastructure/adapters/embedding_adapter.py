"""向量嵌入适配器

封装 LangChain 的 HuggingFaceEmbeddings，提供统一的 embedding 接口。
作为基础设施层适配器，为领域层和应用层提供向量计算能力。
"""

import os
from typing import Optional

from langchain_huggingface import HuggingFaceEmbeddings

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class EmbeddingAdapter:
    """向量嵌入适配器

    封装 LangChain 的 HuggingFaceEmbeddings，提供统一的 embedding 接口。
    支持单条和批量文本向量化。

    设计原则：
    - Context Enrichment：计算向量时拼接上下文
    - 复用 LangChain 组件
    - 支持依赖注入（便于测试）
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cuda",
    ) -> None:
        """初始化 Embedding 适配器

        Args:
            model_path: 模型路径，默认使用配置中的路径
            device: 运行设备（cuda/cpu）
        """
        settings = get_settings()
        self._model_path = model_path or settings.embedding_model_path
        self._device = device

        if not os.path.exists(self._model_path):
            raise FileNotFoundError(f"Model not found at: {self._model_path}")

        self._embeddings = HuggingFaceEmbeddings(
            model_name=self._model_path,
            model_kwargs={"device": self._device},
        )

        logger.info(
            f"EmbeddingAdapter initialized: model={self._model_path}, "
            f"dimension={settings.qdrant_vector_size}"
        )

    def embed(self, text: str) -> list[float]:
        """单条文本向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表
        """
        try:
            return self._embeddings.embed_query(text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表
        """
        try:
            return self._embeddings.embed_documents(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise

    @property
    def dimension(self) -> int:
        """获取向量维度"""
        return get_settings().qdrant_vector_size


# 单例获取函数（用于生产环境）
_embedding_adapter: Optional[EmbeddingAdapter] = None


def get_embedding_adapter() -> EmbeddingAdapter:
    """获取 Embedding 适配器单例

    Returns:
        EmbeddingAdapter 实例
    """
    global _embedding_adapter
    if _embedding_adapter is None:
        _embedding_adapter = EmbeddingAdapter()
    return _embedding_adapter


__all__ = [
    "EmbeddingAdapter",
    "get_embedding_adapter",
]