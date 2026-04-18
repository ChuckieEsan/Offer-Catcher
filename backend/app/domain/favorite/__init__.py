"""Favorite Domain - 收藏领域

领域职责：
- 用户对题目的收藏行为管理
- 收藏幂等性规则
"""

from app.domain.favorite.aggregates import Favorite
from app.domain.favorite.repositories import FavoriteRepository

__all__ = [
    "Favorite",
    "FavoriteRepository",
]