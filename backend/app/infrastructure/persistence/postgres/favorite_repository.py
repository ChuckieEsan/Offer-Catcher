"""Favorite Repository - PostgreSQL 实现

实现 FavoriteRepository Protocol，基于 PostgreSQL 持久化。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。

使用直接 SQL 操作，不依赖 PostgresClient 的业务方法。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Dict, Optional

from app.domain.favorite.aggregates import Favorite
from app.infrastructure.persistence.postgres.client import PostgresClient
from app.infrastructure.common.logger import logger


class PostgresFavoriteRepository:
    """收藏仓库的 PostgreSQL 实现

    实现了 FavoriteRepository Protocol 的所有方法。
    使用直接 SQL 操作，不依赖 PostgresClient 的业务方法。

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
        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, question_id, created_at
                FROM favorites WHERE user_id = %s AND question_id = %s
                """,
                (user_id, question_id),
            )
            row = cur.fetchone()

        if row is None:
            return None

        return Favorite(
            favorite_id=row[0],
            user_id=row[1],
            question_id=row[2],
            created_at=row[3],
        )

    def find_all_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Favorite]:
        """获取用户所有收藏"""
        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, question_id, created_at
                FROM favorites WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()

        return [
            Favorite(
                favorite_id=row[0],
                user_id=row[1],
                question_id=row[2],
                created_at=row[3],
            )
            for row in rows
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

        # 直接 SQL 插入
        now = datetime.now()
        favorite_id = str(uuid.uuid4())

        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO favorites (id, user_id, question_id, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (favorite_id, favorite.user_id, favorite.question_id, now),
            )
            self._client.conn.commit()

        logger.info(f"Favorite saved: {favorite_id}")

    def delete(self, user_id: str, question_id: str) -> bool:
        """删除收藏"""
        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM favorites WHERE user_id = %s AND question_id = %s
                """,
                (user_id, question_id),
            )
            self._client.conn.commit()
            return cur.rowcount > 0

    def count_by_user(self, user_id: str) -> int:
        """统计用户收藏数量"""
        with self._client.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM favorites WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def check_exists(
        self,
        user_id: str,
        question_ids: List[str],
    ) -> Dict[str, bool]:
        """批量检查收藏状态"""
        if not question_ids:
            return {}

        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                SELECT question_id FROM favorites
                WHERE user_id = %s AND question_id IN %s
                """,
                (user_id, tuple(question_ids)),
            )
            rows = cur.fetchall()

        existing_ids = {row[0] for row in rows}
        return {qid: qid in existing_ids for qid in question_ids}


def get_favorite_repository() -> PostgresFavoriteRepository:
    """获取收藏仓库实例"""
    from app.infrastructure.persistence.postgres import get_postgres_client

    client = get_postgres_client()
    return PostgresFavoriteRepository(client)


__all__ = [
    "PostgresFavoriteRepository",
    "get_favorite_repository",
]