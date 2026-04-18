"""Search API - 向量检索接口

提供语义搜索能力，使用 DDD 架构。
"""

from fastapi import APIRouter

from app.application.services.retrieval_service import get_retrieval_service
from app.api.dto.search_dto import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    to_search_result_item,
)
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/search", tags=["search"])


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

    # 转换为 DTO
    items = [to_search_result_item(r) for r in results]

    return SearchResponse(results=items)


__all__ = ["router"]