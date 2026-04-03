"""检索流水线模块

处理数据检索流程：
1. 输入：查询文本 + 可选过滤条件
2. 使用 QdrantManager 执行检索（扁平结构）
3. 返回 SearchResult 列表

直接使用 app/db 模块。
"""

from typing import Optional, List

from app.models.schemas import SearchResult, SearchFilter
from app.db.qdrant_client import get_qdrant_manager
from app.tools.embedding import get_embedding_tool
from app.utils.logger import logger


class RetrievalPipeline:
    """检索流水线

    负责处理查询检索，结合语义搜索和元数据过滤。
    直接使用 QdrantManager 执行检索。
    """

    def __init__(self) -> None:
        """初始化检索流水线"""
        self.qdrant_manager = get_qdrant_manager()
        self.embedding_tool = get_embedding_tool()
        # 确保集合存在
        self.qdrant_manager.create_collection_if_not_exists()
        logger.info("RetrievalPipeline initialized")

    def search(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        mastery_level: Optional[int] = None,
        question_type: Optional[str] = None,
        core_entities: Optional[List[str]] = None,
        cluster_ids: Optional[List[str]] = None,
        k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """搜索

        使用 QdrantManager 执行检索。

        Args:
            query: 查询文本
            company: 公司名称过滤
            position: 岗位名称过滤
            mastery_level: 熟练度等级过滤
            question_type: 题目类型过滤
            core_entities: 知识点过滤（匹配任一知识点）
            cluster_ids: 考点簇过滤（匹配任一簇）
            k: 返回结果数量
            score_threshold: 最低相似度阈值

        Returns:
            SearchResult 列表
        """
        # 生成查询向量
        query_vector = self.embedding_tool.embeddings.embed_query(query)

        # 构建过滤条件
        filter_conditions = None
        if any([company, position, mastery_level, question_type, core_entities, cluster_ids]):
            filter_conditions = SearchFilter(
                company=company,
                position=position,
                mastery_level=mastery_level,
                question_type=question_type,
                core_entities=core_entities,
                cluster_ids=cluster_ids,
            )

        # 执行检索
        results = self.qdrant_manager.search(
            query_vector=query_vector,
            filter_conditions=filter_conditions,
            limit=k,
            score_threshold=score_threshold,
        )

        logger.info(
            f"Search completed: query='{query}', results={len(results)}"
        )

        return results


# 全局单例
_retrieval_pipeline: Optional[RetrievalPipeline] = None


def get_retrieval_pipeline() -> RetrievalPipeline:
    """获取检索流水线单例"""
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        _retrieval_pipeline = RetrievalPipeline()
    return _retrieval_pipeline