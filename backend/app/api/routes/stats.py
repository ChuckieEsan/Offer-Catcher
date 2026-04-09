"""Stats API - 统计数据接口

提供仪表盘数据。
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional, Dict
from collections import defaultdict

from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.graph_client import get_graph_client
from app.db.qdrant_client import get_qdrant_manager
from app.services.cache_service import get_cache_service, CacheKeys
from app.utils.logger import logger

router = APIRouter(prefix="/stats", tags=["stats"])


# ========== Response Models ==========

class OverviewResponse(BaseModel):
    """总览统计响应"""
    total_questions: int
    total_companies: int
    total_positions: int
    by_type: Dict[str, int]
    by_mastery: Dict[int, int]
    has_answer: int
    no_answer: int


class CompanyStats(BaseModel):
    """公司统计"""
    company: str
    count: int
    mastered: int
    has_answer: int


class EntityStats(BaseModel):
    """考点统计"""
    entity: str
    count: int


class ClusterStats(BaseModel):
    """聚类统计"""
    cluster_id: str
    count: int


# ========== API Endpoints ==========

@router.get("/overview", response_model=OverviewResponse)
async def get_overview():
    """获取总览统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get stats overview")

    pipeline = get_retrieval_pipeline()
    cache = get_cache_service()

    def fetch_overview():
        results = pipeline.search(query="", k=10000)

        # 统计
        companies = set()
        positions = set()
        by_type = defaultdict(int)
        by_mastery = defaultdict(int)
        has_answer = 0
        no_answer = 0

        for r in results:
            companies.add(r.company)
            positions.add(r.position)
            by_type[r.question_type] += 1
            by_mastery[r.mastery_level] += 1
            if r.question_answer:
                has_answer += 1
            else:
                no_answer += 1

        return OverviewResponse(
            total_questions=len(results),
            total_companies=len(companies),
            total_positions=len(positions),
            by_type=dict(by_type),
            by_mastery=dict(by_mastery),
            has_answer=has_answer,
            no_answer=no_answer
        )

    return cache.get_stats(CacheKeys.stats_overview(), fetch_overview)


@router.get("/companies", response_model=List[CompanyStats])
async def get_company_stats():
    """获取各公司统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get company stats")

    pipeline = get_retrieval_pipeline()
    cache = get_cache_service()

    def fetch_company_stats():
        results = pipeline.search(query="", k=10000)

        # 按公司分组统计
        company_data = defaultdict(lambda: {"count": 0, "mastered": 0, "has_answer": 0})

        for r in results:
            company_data[r.company]["count"] += 1
            if r.mastery_level == 2:
                company_data[r.company]["mastered"] += 1
            if r.question_answer:
                company_data[r.company]["has_answer"] += 1

        # 转换为列表并排序
        stats = [
            CompanyStats(
                company=company,
                count=data["count"],
                mastered=data["mastered"],
                has_answer=data["has_answer"]
            )
            for company, data in company_data.items()
        ]

        return sorted(stats, key=lambda x: x.count, reverse=True)

    return cache.get_stats(CacheKeys.stats_companies(), fetch_company_stats)


@router.get("/entities", response_model=List[EntityStats])
async def get_entity_stats(
    company: Optional[str] = Query(None, description="公司过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量")
):
    """获取热门考点统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info(f"Get entity stats: company={company}, limit={limit}")

    cache = get_cache_service()
    graph_client = get_graph_client()

    # 构建缓存 key
    cache_key = f"{CacheKeys.PREFIX}:stats:entities:{company or 'all'}:{limit}"

    def fetch_entity_stats():
        # graph_client.get_top_entities 会自动处理连接
        top_entities = graph_client.get_top_entities(company=company, limit=limit)

        return [
            EntityStats(entity=e["entity"], count=e["count"])
            for e in top_entities
        ]

    return cache.get_stats(cache_key, fetch_entity_stats)


@router.get("/clusters", response_model=List[ClusterStats])
async def get_cluster_stats():
    """获取聚类统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get cluster stats")

    qdrant = get_qdrant_manager()
    cache = get_cache_service()

    def fetch_cluster_stats():
        all_questions = qdrant.scroll_all(limit=10000)

        # 按 cluster_ids 分组统计
        cluster_data = defaultdict(int)
        for q in all_questions:
            if q.cluster_ids:
                for cluster_id in q.cluster_ids:
                    cluster_data[cluster_id] += 1

        # 转换为列表并排序
        stats = [
            ClusterStats(cluster_id=cluster_id, count=count)
            for cluster_id, count in cluster_data.items()
        ]

        return sorted(stats, key=lambda x: x.count, reverse=True)

    return cache.get_stats(CacheKeys.stats_clusters(), fetch_cluster_stats)