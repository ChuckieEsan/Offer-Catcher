"""Favorite Application Service - 收藏应用服务

提供收藏管理的用例编排：
- 添加收藏
- 取消收藏
- 获取收藏列表
- 批量检查收藏状态

应用层职责：
- 协调领域对象（Favorite 聚合）
- 调用 Repository
- 发布领域事件（可选）
"""

from __future__ import annotations

from typing import List, Dict

from app.domain.favorite.aggregates import Favorite
from app.domain.favorite.repositories import FavoriteRepository
from app.infrastructure.common.logger import logger


class FavoriteApplicationService:
    """收藏应用服务

    用例编排：
    - add: 添加收藏（幂等性检查在 Repository.save 中）
    - remove: 取消收藏
    - list: 获取收藏列表
    - check: 批量检查收藏状态
    - count: 统计收藏数量
    """

    def __init__(self, repository: FavoriteRepository):
        self._repository = repository

    def add(self, user_id: str, question_id: str) -> Favorite:
        """添加收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            Favorite 聚合根

        Raises:
            ValueError: 已收藏时抛出异常
        """
        logger.info(f"Add favorite: user={user_id}, question={question_id}")

        # 创建聚合根
        favorite = Favorite.create(user_id=user_id, question_id=question_id)

        # 保存（幂等性检查在 Repository 中）
        self._repository.save(favorite)

        return favorite

    def remove(self, user_id: str, question_id: str) -> bool:
        """取消收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            是否成功删除
        """
        logger.info(f"Remove favorite: user={user_id}, question={question_id}")

        return self._repository.delete(user_id, question_id)

    def list(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Favorite], int]:
        """获取收藏列表

        Args:
            user_id: 用户 ID
            page: 页码
            page_size: 每页数量

        Returns:
            (favorites, total) 元组
        """
        logger.info(f"List favorites: user={user_id}, page={page}")

        offset = (page - 1) * page_size
        favorites = self._repository.find_all_by_user(
            user_id,
            limit=page_size,
            offset=offset,
        )
        total = self._repository.count_by_user(user_id)

        return favorites, total

    def check(self, user_id: str, question_ids: List[str]) -> Dict[str, bool]:
        """批量检查收藏状态

        Args:
            user_id: 用户 ID
            question_ids: 题目 ID 列表

        Returns:
            question_id -> is_favored 映射
        """
        logger.info(f"Check favorites: user={user_id}, count={len(question_ids)}")

        return self._repository.check_exists(user_id, question_ids)

    def count(self, user_id: str) -> int:
        """统计收藏数量

        Args:
            user_id: 用户 ID

        Returns:
            收藏数量
        """
        return self._repository.count_by_user(user_id)

    def is_favored(self, user_id: str, question_id: str) -> bool:
        """检查是否已收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            是否已收藏
        """
        favorite = self._repository.find_by_user_and_question(user_id, question_id)
        return favorite is not None


def get_favorite_service() -> FavoriteApplicationService:
    """获取收藏应用服务实例"""
    from app.infrastructure.persistence.postgres.favorite_repository import (
        get_favorite_repository,
    )

    repository = get_favorite_repository()
    return FavoriteApplicationService(repository)


__all__ = [
    "FavoriteApplicationService",
    "get_favorite_service",
]