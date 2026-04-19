"""检索应用服务

提供题目检索能力，支持：
1. 基础向量检索（Payload 预过滤 + 向量计算）
2. 两阶段检索（向量召回 + Rerank 精排）

作为应用层服务，编排：
- QuestionRepository：向量检索
- EmbeddingAdapter：计算查询向量
- RerankerAdapter：重排精排（可选）
"""

from typing import Optional

from app.domain.question.repositories import QuestionRepository
from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.infrastructure.adapters.embedding_adapter import (
    EmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.adapters.reranker_adapter import (
    RerankerAdapter,
    get_reranker_adapter,
)
from app.infrastructure.common.cache import singleton
from app.infrastructure.common.logger import logger
from app.infrastructure.persistence.qdrant.payloads import SearchResult


class RetrievalApplicationService:
    """检索应用服务

    提供题目检索能力：
    1. 基础向量检索：使用 QuestionRepository 执行 Payload 预过滤 + 向量计算
    2. 两阶段检索：向量召回（多候选）+ Rerank 精排

    检索流程：
    - 输入：查询文本 + 可选过滤条件
    - 使用 EmbeddingAdapter 计算查询向量
    - 使用 QuestionRepository 执行检索
    - 可选使用 RerankerAdapter 精排
    - 返回 SearchResult 列表
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
        embedding: Optional[EmbeddingAdapter] = None,
        reranker: Optional[RerankerAdapter] = None,
    ) -> None:
        """初始化检索服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
            embedding: Embedding 适配器（支持依赖注入）
            reranker: Reranker 适配器（支持依赖注入）
        """
        self._question_repo = question_repo or get_question_repository()
        self._embedding = embedding or get_embedding_adapter()
        self._reranker = reranker or get_reranker_adapter()

    def _build_query_context(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
    ) -> str:
        """构建与入库一致的查询上下文

        入库格式："公司：xxx | 岗位：xxx | 类型：xxx | 考点：xxx | 题目：xxx"
        检索时使用相同格式以保证语义对齐。

        Args:
            query: 查询关键词
            company: 公司名称（可选）
            position: 岗位名称（可选）

        Returns:
            拼接后的上下文文本
        """
        parts = []
        parts.append(f"公司：{company or '综合'}")
        parts.append(f"岗位：{position or '综合'}")
        parts.append(f"题目：{query}")
        return " | ".join(parts)

    def _question_to_search_result(self, question, score: float = 0.0) -> SearchResult:
        """将 Question 聚合转换为 SearchResult

        Args:
            question: Question 实例
            score: 相似度分数

        Returns:
            SearchResult 实例
        """
        return SearchResult(
            question_id=question.question_id,
            question_text=question.question_text,
            company=question.company,
            position=question.position,
            mastery_level=question.mastery_level.value,
            question_type=question.question_type.value,
            core_entities=question.core_entities,
            cluster_ids=question.cluster_ids,
            metadata=question.metadata,
            question_answer=question.answer,
            score=score,
        )

    def search(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        mastery_level: Optional[int] = None,
        question_type: Optional[str] = None,
        core_entities: Optional[list[str]] = None,
        cluster_ids: Optional[list[str]] = None,
        k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """基础向量检索

        使用 QuestionRepository 执行 Payload 预过滤 + 向量计算。

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
        # 构建查询上下文
        context = self._build_query_context(query, company, position)

        # 计算查询向量
        query_vector = self._embedding.embed(context)

        # 构建过滤条件
        filter_conditions = None
        if any([company, position, mastery_level, question_type, core_entities, cluster_ids]):
            filter_conditions = {
                "company": company,
                "position": position,
                "mastery_level": mastery_level,
                "question_type": question_type,
                "core_entities": core_entities,
                "cluster_ids": cluster_ids,
            }

        # 执行检索（返回带 score 的结果）
        search_results = self._question_repo.search(
            query_vector=query_vector,
            filter_conditions=filter_conditions,
            limit=k,
            score_threshold=score_threshold,
        )

        # 转换为 SearchResult
        results = [
            self._question_to_search_result(question, score)
            for question, score in search_results
        ]

        logger.info(f"Search completed: query='{query}', results={len(results)}")

        return results

    def search_with_rerank(
        self,
        query: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        k: int = 5,
        recall_multiplier: int = 3,
    ) -> list[SearchResult]:
        """两阶段检索（向量召回 + Rerank 精排）

        第一阶段：向量召回多候选（k * recall_multiplier）
        第二阶段：Rerank 精排，返回 top_k

        Args:
            query: 查询关键词
            company: 公司名称（用于语义增强）
            position: 岗位名称（用于语义增强）
            k: 最终返回数量
            recall_multiplier: 召回倍数（召回 k * multiplier 个候选）

        Returns:
            SearchResult 列表（已精排）
        """
        # 构建查询上下文
        context = self._build_query_context(query, company, position)

        # 计算查询向量
        query_vector = self._embedding.embed(context)

        # Stage 1: 向量召回（多候选）
        recall_limit = k * recall_multiplier
        search_results = self._question_repo.search(
            query_vector=query_vector,
            limit=recall_limit,
        )

        if not search_results:
            logger.info(f"Search with rerank: no candidates found for '{query}'")
            return []

        # 提取 Question（丢弃 score，后续用 rerank score）
        candidates = [question for question, _ in search_results]

        # Stage 2: Rerank 精排
        candidate_texts = [q.question_text for q in candidates]
        ranked_indices = self._reranker.rerank(query, candidate_texts, top_k=k)

        # 根据重排结果重组 SearchResult
        results = []
        for idx, rerank_score in ranked_indices:
            question = candidates[idx]
            result = self._question_to_search_result(question, score=rerank_score)
            results.append(result)

        logger.info(
            f"Search with rerank completed: query='{query}', "
            f"recall={len(candidates)}, rerank_top={len(results)}"
        )

        return results


@singleton
def get_retrieval_service() -> RetrievalApplicationService:
    """获取检索服务单例

    Returns:
        RetrievalApplicationService 实例
    """
    return RetrievalApplicationService()


__all__ = [
    "RetrievalApplicationService",
    "get_retrieval_service",
]