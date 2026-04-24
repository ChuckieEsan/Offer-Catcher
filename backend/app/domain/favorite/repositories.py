"""Favorite Domain - Repository Protocol

定义收藏领域的仓库接口（Protocol）。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。
"""

from __future__ import annotations

from typing import Protocol, List, Dict, runtime_checkable

from app.domain.favorite.aggregates import Favorite


@runtime_checkable
class FavoriteRepository(Protocol):
    """收藏仓库协议

    定义收藏聚合的持久化接口。
    任何实现了这些方法的类都会被类型检查器识别为 FavoriteRepository。

    Methods:
        find_by_user_and_question: 查找特定收藏
        find_all_by_user: 获取用户所有收藏
        save: 保存收藏
        delete: 删除收藏
        count_by_user: 统计收藏数量
        check_exists: 批量检查收藏状态
    """

    def find_by_user_and_question(
        self,
        user_id: str,
        question_id: str,
    ) -> Favorite | None:
        """查找特定收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            Favorite 聚合根，不存在时返回 None
        """
        ...

    def find_all_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Favorite]:
        """获取用户所有收藏

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            Favorite 聚合根列表
        """
        ...

    def save(self, favorite: Favorite) -> None:
        """保存收藏

        Args:
            favorite: Favorite 聚合根

        Raises:
            ValueError: 已存在时抛出异常（幂等性检查）
        """
        ...

    def delete(self, user_id: str, question_id: str) -> bool:
        """删除收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            是否成功删除
        """
        ...

    def count_by_user(self, user_id: str) -> int:
        """统计用户收藏数量

        Args:
            user_id: 用户 ID

        Returns:
            收藏数量
        """
        ...

    def check_exists(
        self,
        user_id: str,
        question_ids: List[str],
    ) -> Dict[str, bool]:
        """批量检查收藏状态

        Args:
            user_id: 用户 ID
            question_ids: 题目 ID 列表

        Returns:
            question_id -> is_favored 映射
        """
        ...


__all__ = ["FavoriteRepository"]