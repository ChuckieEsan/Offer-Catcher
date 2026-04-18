"""Favorites API - 题目收藏接口

提供题目的收藏、取消收藏、收藏列表查询等功能。
使用 DDD 架构：Application Service 编排用例，DTO 传输数据。
"""

from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional

from app.application.services.favorite_service import get_favorite_service
from app.api.dto.favorite_dto import (
    AddFavoriteRequest,
    FavoriteItem,
    FavoriteListResponse,
    CheckFavoritesRequest,
    CheckFavoritesResponse,
    favorite_to_response,
)
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/favorites", tags=["favorites"])


# ========== Helper Functions ==========


def get_user_id(x_user_id: Optional[str] = None) -> str:
    """获取用户 ID"""
    return x_user_id or "default_user"


# ========== API Endpoints ==========


@router.post("", response_model=FavoriteItem)
async def add_favorite(
    request: AddFavoriteRequest,
    x_user_id: Optional[str] = Header(None),
):
    """添加收藏"""
    user_id = get_user_id(x_user_id)
    logger.info(f"Add favorite: user={user_id}, question={request.question_id}")

    service = get_favorite_service()

    try:
        # 返回 Domain Favorite 聚合
        favorite = service.add(user_id, request.question_id)
        # 转换为 DTO
        return favorite_to_response(favorite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{question_id}")
async def remove_favorite(
    question_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """取消收藏"""
    user_id = get_user_id(x_user_id)
    logger.info(f"Remove favorite: user={user_id}, question={question_id}")

    service = get_favorite_service()
    deleted = service.remove(user_id, question_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="收藏记录不存在")

    return {"success": True}


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    x_user_id: Optional[str] = Header(None),
):
    """获取收藏列表"""
    user_id = get_user_id(x_user_id)
    logger.info(f"List favorites: user={user_id}, page={page}")

    service = get_favorite_service()

    # 返回 Domain Favorite 聚合列表
    favorites, total = service.list(user_id, page=page, page_size=page_size)

    # 转换为 DTO
    return FavoriteListResponse(
        items=[favorite_to_response(f) for f in favorites],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/check", response_model=CheckFavoritesResponse)
async def check_favorites(
    request: CheckFavoritesRequest,
    x_user_id: Optional[str] = Header(None),
):
    """批量检查收藏状态"""
    user_id = get_user_id(x_user_id)
    logger.info(f"Check favorites: user={user_id}, count={len(request.question_ids)}")

    service = get_favorite_service()
    status = service.check(user_id, request.question_ids)

    return CheckFavoritesResponse(status=status)


__all__ = ["router"]