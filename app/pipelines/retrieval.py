"""检索流水线模块

处理数据检索流程：
1. 输入：查询文本 + 可选过滤条件
2. 使用 tools 模块的 VectorSearchTool 执行检索
3. 返回 SearchResult 列表

直接使用 app/tools 模块。
"""

from typing import Optional, List

from app.models.schemas import SearchResult
from app.tools.vector_search import get_vector_search_tool
from app.utils.logger import logger


class RetrievalPipeline:
    """检索流水线

    负责处理查询检索，结合语义搜索和元数据过滤。
    直接复用 app/tools 模块的 VectorSearchTool。
    """

    def __init__(self) -> None:
        """初始化检索流水线"""
        # 复用 tools 模块
        self.vector_search_tool = get_vector_search_tool()
        logger.info("RetrievalPipeline initialized")

    def search(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        mastery_level: Optional[int] = None,
        question_type: Optional[str] = None,
        k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """搜索

        使用 tools 模块的 VectorSearchTool 执行检索。

        Args:
            query: 查询文本
            company: 公司名称过滤
            position: 岗位名称过滤
            mastery_level: 熟练度等级过滤
            question_type: 题目类型过滤
            k: 返回结果数量
            score_threshold: 最低相似度阈值

        Returns:
            SearchResult 列表
        """
        results = self.vector_search_tool.search_similar(
            query=query,
            company=company,
            position=position,
            mastery_level=mastery_level,
            question_type=question_type,
            top_k=k,
            score_threshold=score_threshold,
        )

        logger.info(
            f"Search completed: query='{query}', results={len(results)}"
        )

        return results


# 全局单例
_retrieval_pipeline: Optional[RetrievalPipeline] = None


def get_retrieval_pipeline() -> RetrievalPipeline:
    """获取检索流水线单例

    Returns:
        RetrievalPipeline 实例
    """
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        _retrieval_pipeline = RetrievalPipeline()
    return _retrieval_pipeline