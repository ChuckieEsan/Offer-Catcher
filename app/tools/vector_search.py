"""向量检索工具模块

使用 LangChain 的 QdrantVectorStore 进行向量检索。
复用 LangChain 已有组件，避免重复造轮子。

注意：过滤功能采用检索后内存过滤，避免 Qdrant filter 格式问题。
"""

from typing import Optional, List

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config.settings import get_settings
from app.models.schemas import SearchResult
from app.tools.embedding import get_embedding_tool
from app.utils.logger import logger


class VectorSearchTool:
    """向量检索工具

    使用 LangChain 的 QdrantVectorStore，提供向量检索功能。
    支持直接输入文本自动 embedding 后检索。
    过滤功能采用检索后内存过滤。
    """

    def __init__(self) -> None:
        """初始化向量检索工具"""
        self.settings = get_settings()
        self.embedding_tool = get_embedding_tool()
        self._vectorstore: Optional[QdrantVectorStore] = None
        logger.info("Vector search tool initialized")

    @property
    def vectorstore(self) -> QdrantVectorStore:
        """获取 QdrantVectorStore 实例（延迟加载）"""
        if self._vectorstore is None:
            client = QdrantClient(url=self.settings.qdrant_url)
            self._vectorstore = QdrantVectorStore(
                client=client,
                collection_name=self.settings.qdrant_collection,
                embedding=self.embedding_tool.embeddings,
            )
            logger.info(
                f"QdrantVectorStore initialized: collection={self.settings.qdrant_collection}"
            )
        return self._vectorstore

    def _filter_results(
        self,
        docs: List[Document],
        company: Optional[str] = None,
        position: Optional[str] = None,
        mastery_level: Optional[int] = None,
        question_type: Optional[str] = None,
    ) -> List[Document]:
        """内存过滤结果

        Args:
            docs: 检索到的文档列表
            company: 公司名称过滤
            position: 岗位名称过滤
            mastery_level: 熟练度等级过滤
            question_type: 题目类型过滤

        Returns:
            过滤后的文档列表
        """
        filtered = []
        for doc in docs:
            metadata = doc.metadata

            if company and metadata.get("company") != company:
                continue
            if position and metadata.get("position") != position:
                continue
            if mastery_level is not None and metadata.get("mastery_level") != mastery_level:
                continue
            if question_type and metadata.get("question_type") != question_type:
                continue

            filtered.append(doc)

        return filtered

    def _convert_to_search_result(self, doc: Document, score: float = 0.0) -> SearchResult:
        """转换为 SearchResult"""
        metadata = doc.metadata
        return SearchResult(
            question_id=metadata.get("question_id", ""),
            question_text=metadata.get("question_text", ""),
            company=metadata.get("company", ""),
            position=metadata.get("position", ""),
            mastery_level=metadata.get("mastery_level", 0),
            question_type=metadata.get("question_type", ""),
            question_answer=None,
            score=score,
        )

    def search_similar(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        question_type: Optional[str] = None,
        mastery_level: Optional[int] = None,
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """相似度检索（带过滤条件）

        支持直接输入文本，自动 embedding 后检索。
        过滤采用检索后内存过滤。

        Args:
            query: 查询文本
            company: 公司名称过滤（可选）
            position: 岗位名称过滤（可选）
            question_type: 题目类型过滤（可选）
            mastery_level: 熟练度等级过滤（可选）
            top_k: 返回结果数量，默认 10
            score_threshold: 最低相似度阈值（可选）

        Returns:
            检索结果列表
        """
        # 获取更多结果用于过滤
        search_k = top_k * 2 if any([company, position, mastery_level, question_type]) else top_k

        # 构建搜索参数（暂不支持 score_threshold）
        search_kwargs = {"k": search_k}

        # 获取 retriever 并搜索
        retriever = self.vectorstore.as_retriever(
            search_kwargs=search_kwargs
        )
        docs = retriever.invoke(query)

        # 内存过滤
        if any([company, position, mastery_level, question_type]):
            docs = self._filter_results(
                docs, company, position, mastery_level, question_type
            )
            docs = docs[:top_k]

        logger.info(
            f"Search completed: query='{query[:30]}...', "
            f"results={len(docs)}"
        )

        return [self._convert_to_search_result(doc) for doc in docs]

    def similarity_search_with_score(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        mastery_level: Optional[int] = None,
        question_type: Optional[str] = None,
        k: int = 10,
    ) -> List[SearchResult]:
        """带分数的相似度搜索

        Args:
            query: 查询文本
            company: 公司名称过滤
            position: 岗位名称过滤
            mastery_level: 熟练度等级过滤
            question_type: 题目类型过滤
            k: 返回结果数量

        Returns:
            检索结果列表（包含分数）
        """
        search_k = k * 2 if any([company, position, mastery_level, question_type]) else k

        docs_and_scores = self.vectorstore.similarity_search_with_score(
            query=query,
            k=search_k,
        )

        # 转换为结果
        results = []
        for doc, score in docs_and_scores:
            results.append(self._convert_to_search_result(doc, float(score)))

        # 内存过滤
        if any([company, position, mastery_level, question_type]):
            results = [
                r for r in results
                if (not company or r.company == company)
                and (not position or r.position == position)
                and (mastery_level is None or r.mastery_level == mastery_level)
                and (not question_type or r.question_type == question_type)
            ]
            results = results[:k]

        logger.info(
            f"Similarity search completed: query='{query[:30]}...', "
            f"results={len(results)}"
        )

        return results


# 全局单例
_vector_search_tool: Optional[VectorSearchTool] = None


def get_vector_search_tool() -> VectorSearchTool:
    """获取向量检索工具单例

    Returns:
        VectorSearchTool 实例
    """
    global _vector_search_tool
    if _vector_search_tool is None:
        _vector_search_tool = VectorSearchTool()
    return _vector_search_tool


# 导出 LangChain 组件
__all__ = [
    "VectorSearchTool",
    "get_vector_search_tool",
    "QdrantVectorStore",
]