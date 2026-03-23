"""文本向量化工具模块

使用 LangChain 的 SentenceTransformerEmbeddings 进行文本向量化。
复用 LangChain 已有组件，避免重复造轮子。
"""

import os
from pathlib import Path
from typing import Optional

from langchain_community.embeddings import SentenceTransformerEmbeddings

from app.config.settings import get_settings
from app.utils.logger import logger

# 模型路径
MODEL_DIR = Path(__file__).parent.parent.parent / "models"
BGE_M3_MODEL_PATH = str(MODEL_DIR / "bge-m3")


class EmbeddingTool:
    """文本向量化工具

    封装 LangChain 的 SentenceTransformerEmbeddings，提供统一的 embedding 接口。
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
            model_path: 模型路径，默认使用 models/bge-m3
        """
        self.model_path = model_path or BGE_M3_MODEL_PATH
        self._embeddings: Optional[SentenceTransformerEmbeddings] = None

    @property
    def embeddings(self) -> SentenceTransformerEmbeddings:
        """获取 Embeddings 实例（延迟加载）"""
        if self._embeddings is None:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model not found at: {self.model_path}")

            self._embeddings = SentenceTransformerEmbeddings(
                model_name=self.model_path,
                model_kwargs={"device": "cpu"},
            )
            # 获取向量维度
            settings = get_settings()
            logger.info(
                f"Embedding tool initialized with model: {self.model_path}, "
                f"dimension: {settings.qdrant_vector_size}"
            )
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

    def embed_with_context(
        self,
        question_text: str,
        company: str,
        position: str,
    ) -> list[float]:
        """上下文拼接后向量化（Context Enrichment）

        遵循 CLAUDE.md 中的设计原则：
        计算向量时不要只嵌入题目，必须拼接上下文：
        "公司：字节跳动 | 岗位：Agent应用开发 | 题目：qlora怎么优化显存？"

        Args:
            question_text: 题目文本
            company: 公司名称
            position: 岗位名称

        Returns:
            向量列表
        """
        # 上下文拼接
        context_text = f"公司：{company} | 岗位：{position} | 题目：{question_text}"
        logger.debug(f"Context enriched text: {context_text}")

        return self.embed_text(context_text)

    def embed_questions(
        self,
        questions: list[dict],
    ) -> list[list[float]]:
        """批量题目向量化（带上下文）

        适用于批量入库场景。

        Args:
            questions: 题目列表，每项包含 question_text, company, position

        Returns:
            向量列表
        """
        context_texts = []
        for q in questions:
            context = f"公司：{q['company']} | 岗位：{q['position']} | 题目：{q['question_text']}"
            context_texts.append(context)

        return self.embed_texts(context_texts)


# 全局单例
_embedding_tool: Optional[EmbeddingTool] = None


def get_embedding_tool() -> EmbeddingTool:
    """获取 Embedding 工具单例

    Returns:
        EmbeddingTool 实例
    """
    global _embedding_tool
    if _embedding_tool is None:
        _embedding_tool = EmbeddingTool()
    return _embedding_tool


# 导出 LangChain 组件
__all__ = [
    "EmbeddingTool",
    "get_embedding_tool",
    "SentenceTransformerEmbeddings",
]