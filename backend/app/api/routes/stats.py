"""Stats API - 统计数据接口

提供仪表盘数据。
使用 Application 层的 StatsApplicationService 获取数据，
response_model 直接使用 Application 层的输出类型。
"""

from fastapi import APIRouter, Query
from typing import Optional, List

from app.application.services.stats_service import (
    get_stats_service,
    OverviewStats,
    CompanyStats,
    EntityStats,
    ClusterStats,
)
from app.utils.logger import logger

router = APIRouter(prefix="/stats", tags=["stats"])


# ========== API Endpoints ==========

@router.get("/overview", response_model=OverviewStats)
async def get_overview():
    """获取总览统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get stats overview")
    service = get_stats_service()
    return service.get_overview()


@router.get("/companies", response_model=List[CompanyStats])
async def get_company_stats():
    """获取各公司统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get company stats")
    service = get_stats_service()
    return service.get_company_stats()


@router.get("/entities", response_model=List[EntityStats])
async def get_entity_stats(
    company: Optional[str] = Query(None, description="公司过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量")
):
    """获取热门考点统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info(f"Get entity stats: company={company}, limit={limit}")
    service = get_stats_service()
    return service.get_entity_stats(company=company, limit=limit)


@router.get("/clusters", response_model=List[ClusterStats])
async def get_cluster_stats():
    """获取聚类统计

    使用缓存优化，TTL 5 分钟兜底。
    """
    logger.info("Get cluster stats")
    service = get_stats_service()
    return service.get_cluster_stats()