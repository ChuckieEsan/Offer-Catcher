"""文本向量化工具模块

使用 LangChain 的 HuggingFaceEmbeddings 进行文本向量化。
复用 LangChain 已有组件，避免重复造轮子。
"""

import os
from typing import Optional

from langchain_huggingface import HuggingFaceEmbeddings

from app.config.settings import get_settings
from app.utils.logger import logger
from app.utils.cache import singleton


class EmbeddingTool:
    """文本向量化工具

    封装 LangChain 的 HuggingFaceEmbeddings，提供统一的 embedding 接口。
    支持单条和批量文本向量化，以及上下文拼接后的向量化。

    遵循的设计原则：
    - Context Enrichment：计算向量时拼接上下文 "公司：xxx | 岗位：xxx | 题目：xxx"
    - 复用 LangChain 组件
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
    ) -> None:
        """初始化 Embedding 工具

        Args:
            model_path: 模型路径，默认使用配置中的路径（models/bge-m3）
        """
        settings = get_settings()
        self.model_path = model_path or settings.embedding_model_path

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found at: {self.model_path}")

        # 直接加载模型（不再延迟加载）
        self._embeddings = HuggingFaceEmbeddings(
            model_name=self.model_path,
            model_kwargs={"device": "cuda"},
        )

        logger.info(
            f"Embedding tool initialized with model: {self.model_path}, "
            f"dimension: {settings.qdrant_vector_size}"
        )

    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        """获取 Embeddings 实例"""
        return self._embeddings

    @property
    def embedding_dimension(self) -> int:
        """获取向量维度"""
        settings = get_settings()
        return settings.qdrant_vector_size

    def embed_text(self, text: str) -> list[float]:
        """单条文本向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表
        """
        try:
            vector = self.embeddings.embed_query(text)
            return vector
        except Exception as e:
            logger.error(f"Failed to embed text: {e}")
            raise

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表
        """
        try:
            vectors = self.embeddings.embed_documents(texts)
            return vectors
        except Exception as e:
            logger.error(f"Failed to embed texts: {e}")
            raise


@singleton
def get_embedding_tool() -> EmbeddingTool:
    """获取 Embedding 工具单例

    Returns:
        EmbeddingTool 实例
    """
    return EmbeddingTool()


__all__ = [
    "EmbeddingTool",
    "get_embedding_tool",
]