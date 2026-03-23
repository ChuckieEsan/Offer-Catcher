"""向量检索工具模块

封装 QdrantManager，提供更便捷的向量检索接口。
支持直接输入文本自动 embedding 后检索，以及带过滤条件的检索。
"""

from typing import Optional

from app.db.qdrant_client import get_qdrant_manager, QdrantManager
from app.models.schemas import SearchFilter, SearchResult
from app.tools.embedding import get_embedding_tool, EmbeddingTool
from app.utils.logger import logger


class VectorSearchTool:
    """向量检索工具

    封装 QdrantManager，提供更便捷的检索接口。
    支持直接输入文本自动 embedding 后检索。

    核心功能：
    - 直接输入文本检索（自动 embedding）
    - 带过滤条件的检索
    - 支持按公司、岗位、熟练度、题目类型过滤
    """

    def __init__(
        self,
        embedding_tool: Optional[EmbeddingTool] = None,
        qdrant_manager: Optional[QdrantManager] = None,
    ) -> None:
        """初始化向量检索工具

        Args:
            embedding_tool: Embedding 工具实例，默认使用全局单例
            qdrant_manager: Qdrant 管理器实例，默认使用全局单例
        """
        self.embedding_tool = embedding_tool or get_embedding_tool()
        self.qdrant_manager = qdrant_manager or get_qdrant_manager()
        logger.info("Vector search tool initialized")

    def search_similar(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        question_type: Optional[str] = None,
        mastery_level: Optional[int] = None,
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """相似度检索（带过滤条件）

        支持直接输入文本，自动 embedding 后检索。

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
        # 1. 将查询文本向量化
        query_vector = self.embedding_tool.embed_text(query)
        logger.debug(f"Query embedded: {len(query_vector)} dims")

        # 2. 构建过滤条件
        filters = None
        if any([company, position, question_type, mastery_level is not None]):
            filters = SearchFilter(
                company=company,
                position=position,
                question_type=question_type,
                mastery_level=mastery_level,
            )

        # 3. 执行检索
        results = self.qdrant_manager.search(
            query_vector=query_vector,
            filter_conditions=filters,
            limit=top_k,
            score_threshold=score_threshold,
        )

        logger.info(
            f"Search completed: query='{query[:30]}...', "
            f"filters={filters}, results={len(results)}"
        )
        return results

    def search_by_company(
        self,
        query: str,
        company: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """按公司检索

        简化接口，专注按公司过滤的场景。

        Args:
            query: 查询文本
            company: 公司名称
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        return self.search_similar(
            query=query,
            company=company,
            top_k=top_k,
        )

    def search_by_position(
        self,
        query: str,
        position: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """按岗位检索

        简化接口，专注按岗位过滤的场景。

        Args:
            query: 查询文本
            position: 岗位名称
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        return self.search_similar(
            query=query,
            position=position,
            top_k=top_k,
        )

    def search_by_mastery_level(
        self,
        query: str,
        mastery_level: int,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """按熟练度等级检索

        简化接口，专注按熟练度过滤的场景。
        用于获取用户未掌握或需要复习的题目。

        Args:
            query: 查询文本
            mastery_level: 熟练度等级（0/1/2）
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        return self.search_similar(
            query=query,
            mastery_level=mastery_level,
            top_k=top_k,
        )

    def get_questions_by_company(
        self,
        company: str,
        question_type: Optional[str] = None,
        mastery_level: Optional[int] = None,
        limit: int = 100,
    ) -> list[SearchResult]:
        """获取指定公司的题目列表

        不需要向量化，直接按条件过滤获取题目列表。

        Args:
            company: 公司名称
            question_type: 题目类型过滤（可选）
            mastery_level: 熟练度等级过滤（可选）
            limit: 返回结果数量

        Returns:
            检索结果列表
        """
        # 使用一个通用查询向量（全零向量）配合过滤条件
        # 实际上更好的方式是添加一个不存在的 question_id 来触发过滤
        # 但这里我们简化为使用文本搜索

        # 构造一个会匹配所有结果的查询
        results = self.search_similar(
            query="*",  # 通用查询
            company=company,
            question_type=question_type,
            mastery_level=mastery_level,
            top_k=limit,
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