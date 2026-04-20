"""Session Summary Repository - PostgreSQL 实现

实现 SessionSummaryRepository Protocol，基于 PostgreSQL 持久化。
支持向量检索（使用 pgvector）。
"""

import uuid
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector

from app.domain.memory.aggregates import SessionSummary
from app.infrastructure.persistence.postgres import get_postgres_client
from app.infrastructure.common.logger import logger


class PostgresSessionSummaryRepository:
    """会话摘要仓库的 PostgreSQL 实现

    实现了 SessionSummaryRepository Protocol 的所有方法。
    使用直接 SQL 操作，支持向量检索。

    设计要点：
    - 支持 CASCADE DELETE（删除对话时自动删除摘要）
    - 支持 pgvector 向量检索
    - 游标存储使用 Redis（由 cursor.py 管理）
    """

    def __init__(self):
        self._client = get_postgres_client()

    def create(self, summary: SessionSummary) -> None:
        """创建会话摘要"""
        with self._client.conn.cursor() as cur:
            embedding_bytes = None
            if summary.embedding:
                # pgvector 需要 register_vector 来处理向量
                register_vector(self._client.conn)
                embedding_bytes = summary.embedding

            cur.execute(
                """
                INSERT INTO session_summaries
                (id, conversation_id, user_id, summary, embedding, message_cursor_uuid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    summary.id,
                    summary.conversation_id,
                    summary.user_id,
                    summary.summary,
                    embedding_bytes,
                    summary.message_cursor_uuid,
                    summary.created_at,
                ),
            )
            self._client.conn.commit()
            logger.info(f"SessionSummary created: {summary.id}")

    def find_by_id(self, summary_id: str) -> SessionSummary | None:
        """根据 ID 查找摘要"""
        with self._client.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, summary, embedding,
                       message_cursor_uuid, created_at
                FROM session_summaries WHERE id = %s
                """,
                (summary_id,),
            )
            row = cur.fetchone()

        if row:
            return self._row_to_summary(row)
        return None

    def find_by_conversation_id(self, conversation_id: str) -> list[SessionSummary]:
        """根据对话 ID 查找所有摘要"""
        with self._client.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, summary, embedding,
                       message_cursor_uuid, created_at
                FROM session_summaries WHERE conversation_id = %s
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()

        return [self._row_to_summary(row) for row in rows]

    def delete_by_conversation_id(self, conversation_id: str) -> int:
        """删除对话的所有摘要（CASCADE DELETE 会自动处理）"""
        with self._client.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM session_summaries WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            self._client.conn.commit()
            return cur.rowcount

    def search_by_embedding(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[SessionSummary]:
        """语义检索摘要"""
        register_vector(self._client.conn)

        with self._client.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, summary, embedding,
                       message_cursor_uuid, created_at,
                       1 - (embedding <=> %s) as similarity
                FROM session_summaries
                WHERE user_id = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (query_embedding, user_id, query_embedding, top_k),
            )
            rows = cur.fetchall()

        return [self._row_to_summary(row) for row in rows]

    def get_recent(self, user_id: str, limit: int = 5) -> list[SessionSummary]:
        """获取用户最近的摘要"""
        with self._client.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, summary, embedding,
                       message_cursor_uuid, created_at
                FROM session_summaries WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

        return [self._row_to_summary(row) for row in rows]

    def _row_to_summary(self, row: dict) -> SessionSummary:
        """将数据库行转换为 SessionSummary 实体"""
        embedding = None
        if row.get("embedding"):
            embedding = list(row["embedding"])

        return SessionSummary(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            summary=row["summary"],
            embedding=embedding,
            message_cursor_uuid=row.get("message_cursor_uuid"),
            created_at=row["created_at"],
        )


def get_session_summary_repository() -> PostgresSessionSummaryRepository:
    """获取会话摘要仓库实例"""
    return PostgresSessionSummaryRepository()


__all__ = [
    "PostgresSessionSummaryRepository",
    "get_session_summary_repository",
]