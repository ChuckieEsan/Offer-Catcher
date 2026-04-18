"""Favorite Domain - 收藏聚合根

定义收藏领域的聚合根。

聚合设计：
- Favorite 聚合根：管理用户对题目的收藏行为

聚合内规则：
- 一个用户对同一题目只能收藏一次（幂等性）
- 收藏创建后不可修改（历史记录）
- 通过 question_id 引用 Question 聚合，不持有 Question 实体
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Favorite(BaseModel):
    """收藏聚合根

    Favorite 是收藏领域的聚合根，记录用户对题目的收藏行为。

    聚合边界规则：
    - 通过 question_id 引用 Question 聚合（跨聚合引用）
    - 不直接持有 Question 实体
    - 收藏创建后不可修改

    Attributes:
        favorite_id: 收藏记录唯一标识
        user_id: 用户 ID
        question_id: 题目 ID（引用 Question 聚合）
        created_at: 收藏时间
    """

    favorite_id: str = Field(description="收藏记录唯一标识")
    user_id: str = Field(description="用户 ID")
    question_id: str = Field(description="题目 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="收藏时间")

    @classmethod
    def create(
        cls,
        user_id: str,
        question_id: str,
        favorite_id: str | None = None,
    ) -> Favorite:
        """创建收藏（工厂方法）

        Args:
            user_id: 用户 ID
            question_id: 题目 ID
            favorite_id: 收藏 ID（可选，自动生成）

        Returns:
            新创建的 Favorite 聚合根
        """
        return cls(
            favorite_id=favorite_id or str(uuid4()),
            user_id=user_id,
            question_id=question_id,
            created_at=datetime.now(),
        )

    def to_payload(self) -> dict:
        """转换为存储 payload"""
        return {
            "favorite_id": self.favorite_id,
            "user_id": self.user_id,
            "question_id": self.question_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> Favorite:
        """从 payload 恢复聚合"""
        return cls(
            favorite_id=payload["favorite_id"],
            user_id=payload["user_id"],
            question_id=payload["question_id"],
            created_at=datetime.fromisoformat(payload["created_at"]),
        )


__all__ = ["Favorite"]