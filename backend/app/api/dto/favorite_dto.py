"""Favorite DTO - 收藏数据传输对象

定义收藏 API 的请求和响应模型。
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


# ========== Request Models ==========


class AddFavoriteRequest(BaseModel):
    """添加收藏请求"""

    question_id: str = Field(description="题目 ID")


class CheckFavoritesRequest(BaseModel):
    """批量检查收藏状态请求"""

    question_ids: List[str] = Field(description="题目 ID 列表")


# ========== Response Models ==========


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


class CheckFavoritesResponse(BaseModel):
    """批量检查收藏状态响应"""

    status: dict[str, bool] = Field(description="question_id -> is_favored")


# ========== DTO Converters ==========


def favorite_to_response(favorite) -> FavoriteItem:
    """将 Favorite 聚合转换为响应 DTO

    Args:
        favorite: Favorite 聚合根

    Returns:
        FavoriteItem DTO
    """
    return FavoriteItem(
        id=favorite.favorite_id,
        question_id=favorite.question_id,
        created_at=favorite.created_at,
    )


__all__ = [
    "AddFavoriteRequest",
    "CheckFavoritesRequest",
    "FavoriteItem",
    "FavoriteListResponse",
    "CheckFavoritesResponse",
    "favorite_to_response",
]