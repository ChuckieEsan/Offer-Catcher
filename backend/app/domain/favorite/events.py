"""Favorite Domain - Domain Events

定义收藏领域的领域事件。
用于跨聚合通信和最终一致性。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FavoriteAdded:
    """收藏添加事件"""

    favorite_id: str
    user_id: str
    question_id: str
    occurred_at: datetime


@dataclass
class FavoriteRemoved:
    """收藏取消事件"""

    user_id: str
    question_id: str
    occurred_at: datetime


__all__ = [
    "FavoriteAdded",
    "FavoriteRemoved",
]