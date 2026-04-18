"""Favorite Repository - PostgreSQL 实现

实现 FavoriteRepository Protocol，基于 PostgreSQL 持久化。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。
"""

from __future__ import annotations

from typing import List, Dict

from app.domain.favorite.aggregates import Favorite
from app.domain.favorite.repositories import FavoriteRepository
from app.infrastructure.persistence.postgres.client import PostgresClient
from app.infrastructure.common.logger import logger


class PostgresFavoriteRepository:
    """收藏仓库的 PostgreSQL 实现

    实现了 FavoriteRepository Protocol 的所有方法。

    设计要点：
    - 返回 Domain Favorite 聚合根
    - 幂等性检查在 save 方法中实现
    """

    def __init__(self, client: PostgresClient):
        self._client = client

    def find_by_user_and_question(
        self,
        user_id: str,
        question_id: str,
    ) -> Favorite | None:
        """查找特定收藏"""
        # 通过 check_favorites 检查是否存在
        status = self._client.check_favorites(user_id, [question_id])
        if not status.get(question_id, False):
            return None

        # 获取收藏列表找到对应记录
        items = self._client.get_favorites(user_id, limit=100)
        for item in items:
            if item["question_id"] == question_id:
                return Favorite(
                    favorite_id=item["id"],
                    user_id=user_id,
                    question_id=question_id,
                    created_at=item["created_at"],
                )

        return None

    def find_all_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Favorite]:
        """获取用户所有收藏"""
        items = self._client.get_favorites(user_id, limit=limit, offset=offset)

        return [
            Favorite(
                favorite_id=item["id"],
                user_id=user_id,
                question_id=item["question_id"],
                created_at=item["created_at"],
            )
            for item in items
        ]

    def save(self, favorite: Favorite) -> None:
        """保存收藏

        Raises:
            ValueError: 已存在时抛出异常
        """
        # 幂等性检查：已存在时抛出异常
        existing = self.find_by_user_and_question(
            favorite.user_id,
            favorite.question_id,
        )
        if existing:
            raise ValueError(f"题目已收藏: {favorite.question_id}")

        # 调用 PostgresClient 添加收藏
        self._client.add_favorite(favorite.user_id, favorite.question_id)
        logger.info(f"Favorite saved: {favorite.favorite_id}")

    def delete(self, user_id: str, question_id: str) -> bool:
        """删除收藏"""
        return self._client.remove_favorite(user_id, question_id)

    def count_by_user(self, user_id: str) -> int:
        """统计用户收藏数量"""
        return self._client.count_favorites(user_id)

    def check_exists(
        self,
        user_id: str,
        question_ids: List[str],
    ) -> Dict[str, bool]:
        """批量检查收藏状态"""
        return self._client.check_favorites(user_id, question_ids)


def get_favorite_repository() -> PostgresFavoriteRepository:
    """获取收藏仓库实例"""
    from app.infrastructure.persistence.postgres import get_postgres_client

    client = get_postgres_client()
    return PostgresFavoriteRepository(client)


__all__ = [
    "PostgresFavoriteRepository",
    "get_favorite_repository",
]