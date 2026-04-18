"""Search API - 向量检索接口

提供语义搜索能力，使用 DDD 架构。
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from app.application.services.retrieval_service import get_retrieval_service
from app.models import SearchResult
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/search", tags=["search"])


# ========== Request/Response Models ==========

class SearchRequest(BaseModel):
    """搜索请求"""
    query: str
    company: Optional[str] = None
    position: Optional[str] = None
    mastery_level: Optional[int] = None
    question_type: Optional[str] = None
    core_entities: Optional[List[str]] = None
    cluster_ids: Optional[List[str]] = None
    k: int = 10
    score_threshold: Optional[float] = None


class SearchResponse(BaseModel):
    """搜索响应"""
    results: List[SearchResult]


# ========== API Endpoints ==========

@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest):
    """语义搜索

    使用 RetrievalApplicationService 执行向量检索。
    Payload 预过滤 + 向量计算。
    """
    logger.info(f"Search: query={request.query}, k={request.k}")

    service = get_retrieval_service()
    results = service.search(
        query=request.query,
        company=request.company,
        position=request.position,
        mastery_level=request.mastery_level,
        question_type=request.question_type,
        core_entities=request.core_entities,
        cluster_ids=request.cluster_ids,
        k=request.k,
        score_threshold=request.score_threshold,
    )

    return SearchResponse(results=results)


__all__ = ["router"]