"""Favorites API - 题目收藏接口

提供题目的收藏、取消收藏、收藏列表查询等功能。
"""

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.infrastructure.persistence.postgres import get_postgres_client
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/favorites", tags=["favorites"])


# ========== Request/Response Models ==========


class AddFavoriteRequest(BaseModel):
    """添加收藏请求"""
    question_id: str = Field(description="题目 ID（MD5 hash）")


class FavoriteItem(BaseModel):
    """收藏记录"""
    id: str = Field(description="收藏记录 ID")
    question_id: str = Field(description="题目 ID")
    created_at: datetime = Field(description="收藏时间")


class FavoriteListResponse(BaseModel):
    """收藏列表响应"""
    items: List[FavoriteItem]
    total: int
    page: int
    page_size: int


class CheckFavoritesRequest(BaseModel):
    """批量检查收藏状态请求"""
    question_ids: List[str] = Field(description="题目 ID 列表")


class CheckFavoritesResponse(BaseModel):
    """批量检查收藏状态响应"""
    status: dict[str, bool] = Field(description="question_id -> is_favored 的映射")


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
    """添加收藏

    Args:
        request: 包含 question_id 的请求
        x_user_id: 用户 ID（Header）

    Returns:
        FavoriteItem 收藏记录
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Add favorite: user={user_id}, question={request.question_id}")

    pg = get_postgres_client()

    try:
        favorite_id = pg.add_favorite(user_id, request.question_id)
        items = pg.get_favorites(user_id, limit=1)
        return FavoriteItem(
            id=favorite_id,
            question_id=request.question_id,
            created_at=items[0]["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{question_id}")
async def remove_favorite(
    question_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """取消收藏

    Args:
        question_id: 题目 ID
        x_user_id: 用户 ID（Header）

    Returns:
        成功/失败状态
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Remove favorite: user={user_id}, question={question_id}")

    pg = get_postgres_client()
    deleted = pg.remove_favorite(user_id, question_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="收藏记录不存在")

    return {"success": True}


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    x_user_id: Optional[str] = Header(None),
):
    """获取收藏列表

    Args:
        page: 页码
        page_size: 每页数量
        x_user_id: 用户 ID（Header）

    Returns:
        FavoriteListResponse 收藏列表
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"List favorites: user={user_id}, page={page}")

    pg = get_postgres_client()

    offset = (page - 1) * page_size
    items = pg.get_favorites(user_id, limit=page_size, offset=offset)
    total = pg.count_favorites(user_id)

    return FavoriteListResponse(
        items=[
            FavoriteItem(
                id=item["id"],
                question_id=item["question_id"],
                created_at=item["created_at"],
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/check", response_model=CheckFavoritesResponse)
async def check_favorites(
    request: CheckFavoritesRequest,
    x_user_id: Optional[str] = Header(None),
):
    """批量检查收藏状态

    用于题目列表页显示收藏图标状态。

    Args:
        request: 包含 question_ids 列表的请求
        x_user_id: 用户 ID（Header）

    Returns:
        CheckFavoritesResponse 收藏状态映射
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Check favorites: user={user_id}, count={len(request.question_ids)}")

    pg = get_postgres_client()
    status = pg.check_favorites(user_id, request.question_ids)

    return CheckFavoritesResponse(status=status)