"""统计应用服务

提供题目统计能力，包括：
1. 总览统计（题目总数、公司数、岗位数等）
2. 公司统计（按公司分组统计题目数、掌握数等）
3. 考点统计（热门知识点）
4. 聚类统计（按 cluster_ids 分组）

作为应用层服务，编排：
- QuestionRepository：获取题目数据
- GraphRepository：获取图数据库统计
- CacheApplicationService：缓存统计结果

输出类型定义在 Application 层，API 层直接使用。
"""

from collections import defaultdict
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.domain.question.repositories import QuestionRepository, GraphRepository
from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.infrastructure.persistence.neo4j import get_graph_client
from app.application.services.cache_service import (
    CacheApplicationService,
    CacheKeys,
    get_cache_service,
)
from app.infrastructure.common.cache import singleton
from app.infrastructure.common.logger import logger


# ========== 输出类型（Application 层） ==========


class OverviewStats(BaseModel):
    """总览统计输出"""

    total_questions: int = Field(description="题目总数")
    total_companies: int = Field(description="公司数")
    total_positions: int = Field(description="岗位数")
    by_type: Dict[str, int] = Field(description="按类型分布")
    by_mastery: Dict[int, int] = Field(description="按熟练度分布")
    has_answer: int = Field(description="有答案数量")
    no_answer: int = Field(description="无答案数量")


class CompanyStats(BaseModel):
    """公司统计输出"""

    company: str = Field(description="公司名称")
    count: int = Field(description="题目数")
    mastered: int = Field(description="已掌握数")
    has_answer: int = Field(description="有答案数")


class EntityStats(BaseModel):
    """考点统计输出"""

    entity: str = Field(description="知识点")
    count: int = Field(description="出现次数")


class ClusterStats(BaseModel):
    """聚类统计输出"""

    cluster_id: str = Field(description="聚类ID")
    count: int = Field(description="题目数")


class PositionStats(BaseModel):
    """岗位统计输出"""

    position: str = Field(description="岗位名称")
    count: int = Field(description="题目数")


# ========== 应用服务 ==========


class StatsApplicationService:
    """统计应用服务

    提供题目统计能力，结果通过缓存优化。
    返回 Pydantic 输出类型，API 层直接使用。
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
        graph_repo: Optional[GraphRepository] = None,
        cache: Optional[CacheApplicationService] = None,
    ) -> None:
        """初始化统计服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
            graph_repo: Graph 仓库（支持依赖注入）
            cache: 缓存服务（支持依赖注入）
        """
        self._question_repo = question_repo or get_question_repository()
        self._graph_repo = graph_repo or get_graph_client()
        self._cache = cache or get_cache_service()

    def get_overview(self) -> OverviewStats:
        """获取总览统计

        使用缓存，TTL 5 分钟。

        Returns:
            OverviewStats
        """

        def fetch() -> OverviewStats:
            questions = self._question_repo.find_all()

            # 统计
            companies = set()
            positions = set()
            by_type = defaultdict(int)
            by_mastery = defaultdict(int)
            has_answer = 0
            no_answer = 0

            for q in questions:
                companies.add(q.company)
                positions.add(q.position)
                by_type[q.question_type.value] += 1
                by_mastery[q.mastery_level.value] += 1
                if q.answer:
                    has_answer += 1
                else:
                    no_answer += 1

            return OverviewStats(
                total_questions=len(questions),
                total_companies=len(companies),
                total_positions=len(positions),
                by_type=dict(by_type),
                by_mastery=dict(by_mastery),
                has_answer=has_answer,
                no_answer=no_answer,
            )

        return self._cache.get_with_lock(
            CacheKeys.stats_overview(),
            fetch,
            ttl=300,
        )

    def get_company_stats(self) -> list[CompanyStats]:
        """获取各公司统计

        使用缓存，TTL 5 分钟。

        Returns:
            CompanyStats 列表
        """

        def fetch() -> list[CompanyStats]:
            questions = self._question_repo.find_all()

            # 按公司分组统计
            company_data = defaultdict(
                lambda: {"count": 0, "mastered": 0, "has_answer": 0}
            )

            for q in questions:
                company_data[q.company]["count"] += 1
                if q.mastery_level.value == 2:
                    company_data[q.company]["mastered"] += 1
                if q.answer:
                    company_data[q.company]["has_answer"] += 1

            # 转换为 CompanyStats 并排序
            stats = [
                CompanyStats(
                    company=company,
                    count=data["count"],
                    mastered=data["mastered"],
                    has_answer=data["has_answer"],
                )
                for company, data in company_data.items()
            ]

            return sorted(stats, key=lambda x: x.count, reverse=True)

        return self._cache.get_with_lock(
            CacheKeys.stats_companies(),
            fetch,
            ttl=300,
        )

    def get_entity_stats(
        self,
        company: Optional[str] = None,
        limit: int = 20,
    ) -> list[EntityStats]:
        """获取热门考点统计

        使用缓存，TTL 5 分钟。

        Args:
            company: 公司过滤（可选）
            limit: 返回数量

        Returns:
            EntityStats 列表
        """
        cache_key = CacheKeys.stats_entities(company, limit)

        def fetch() -> list[EntityStats]:
            top_entities = self._graph_repo.get_top_entities(
                company=company,
                limit=limit,
            )

            return [
                EntityStats(entity=e["entity"], count=e["count"])
                for e in top_entities
            ]

        return self._cache.get_with_lock(cache_key, fetch, ttl=300)

    def get_cluster_stats(self) -> list[ClusterStats]:
        """获取聚类统计

        使用缓存，TTL 5 分钟。

        Returns:
            ClusterStats 列表
        """

        def fetch() -> list[ClusterStats]:
            questions = self._question_repo.find_all()

            # 按 cluster_ids 分组统计
            cluster_data = defaultdict(int)
            for q in questions:
                if q.cluster_ids:
                    for cluster_id in q.cluster_ids:
                        cluster_data[cluster_id] += 1

            # 转换为 ClusterStats 并排序
            stats = [
                ClusterStats(cluster_id=cluster_id, count=count)
                for cluster_id, count in cluster_data.items()
            ]

            return sorted(stats, key=lambda x: x.count, reverse=True)

        return self._cache.get_with_lock(
            CacheKeys.stats_clusters(),
            fetch,
            ttl=300,
        )

    def get_position_stats(self) -> list[PositionStats]:
        """获取岗位统计

        使用缓存，TTL 5 分钟。
        返回所有岗位及其题目数量，按数量降序排列。

        Returns:
            PositionStats 列表
        """

        def fetch() -> list[PositionStats]:
            questions = self._question_repo.find_all()

            # 按岗位分组统计
            position_data = defaultdict(int)
            for q in questions:
                position_data[q.position] += 1

            # 转换为 PositionStats 并排序
            stats = [
                PositionStats(position=position, count=count)
                for position, count in position_data.items()
            ]

            return sorted(stats, key=lambda x: x.count, reverse=True)

        return self._cache.get_with_lock(
            CacheKeys.stats_positions(),
            fetch,
            ttl=300,
        )


@singleton
def get_stats_service() -> StatsApplicationService:
    """获取统计服务单例

    Returns:
        StatsApplicationService 实例
    """
    return StatsApplicationService()


__all__ = [
    "StatsApplicationService",
    "OverviewStats",
    "CompanyStats",
    "EntityStats",
    "ClusterStats",
    "PositionStats",
    "get_stats_service",
]