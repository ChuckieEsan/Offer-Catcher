"""InterviewSession 仓库的 PostgreSQL 实现

实现 InterviewSessionRepository Protocol，基于 PostgreSQL 持久化 InterviewSession 聚合。
"""

import json
from datetime import datetime
from typing import Optional

import psycopg2

from app.domain.interview.aggregates import InterviewSession, InterviewQuestion
from app.domain.interview.repositories import InterviewSessionRepository
from app.domain.shared.enums import SessionStatus, QuestionStatus, DifficultyLevel

from app.infrastructure.persistence.postgres.client import (
    PostgresClient,
    get_postgres_client,
)
from app.infrastructure.common.logger import logger


class PostgresInterviewSessionRepository:
    """InterviewSession 仓库的 PostgreSQL 实现

    实现 InterviewSessionRepository Protocol 的所有方法。
    使用 interview_sessions 表存储面试会话数据。

    表结构：
    - session_id: 会话 ID（主键）
    - user_id: 用户 ID
    - company: 目标公司
    - position: 目标岗位
    - difficulty: 难度
    - total_questions: 题目总数
    - status: 会话状态
    - questions: 题目列表（JSONB）
    - current_question_idx: 当前题目索引
    - correct_count: 答对数量
    - total_score: 总分
    - started_at: 开始时间
    - ended_at: 结束时间
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    def __init__(
        self,
        client: Optional[PostgresClient] = None,
    ) -> None:
        """初始化仓库

        Args:
            client: PostgreSQL 客户端（支持依赖注入）
        """
        self._client = client or get_postgres_client()
        self._ensure_table()

    def _ensure_table(self) -> None:
        """确保 interview_sessions 表存在"""
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_sessions (
                        session_id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        company VARCHAR(100) NOT NULL,
                        position VARCHAR(100) NOT NULL,
                        difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
                        total_questions INTEGER NOT NULL DEFAULT 10,
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        questions JSONB NOT NULL DEFAULT '[]',
                        current_question_idx INTEGER NOT NULL DEFAULT 0,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        total_score INTEGER NOT NULL DEFAULT 0,
                        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        ended_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        UNIQUE(session_id, user_id)
                    )
                    """
                )
                self._client.conn.commit()
            logger.info("interview_sessions table ensured")
        except Exception as e:
            logger.error(f"Failed to create interview_sessions table: {e}")
            self._client.conn.rollback()
            raise

    def find_by_id(self, session_id: str, user_id: str) -> Optional[InterviewSession]:
        """根据 ID 查找会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（用于多租户隔离）

        Returns:
            InterviewSession 实例或 None
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_id, user_id, company, position, difficulty,
                           total_questions, status, questions, current_question_idx,
                           correct_count, total_score, started_at, ended_at,
                           created_at, updated_at
                    FROM interview_sessions
                    WHERE session_id = %s AND user_id = %s
                    """,
                    (session_id, user_id),
                )
                row = cur.fetchone()

            if row is None:
                return None

            return self._row_to_domain(row)

        except Exception as e:
            logger.error(f"Failed to find interview session {session_id}: {e}")
            raise

    def find_by_user(
        self,
        user_id: str,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list[InterviewSession]:
        """查找用户的所有会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            status: 状态过滤（可选）

        Returns:
            InterviewSession 列表
        """
        try:
            sessions = []

            with self._client.conn.cursor() as cur:
                if status:
                    cur.execute(
                        """
                        SELECT session_id, user_id, company, position, difficulty,
                               total_questions, status, questions, current_question_idx,
                               correct_count, total_score, started_at, ended_at,
                               created_at, updated_at
                        FROM interview_sessions
                        WHERE user_id = %s AND status = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, status, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT session_id, user_id, company, position, difficulty,
                               total_questions, status, questions, current_question_idx,
                               correct_count, total_score, started_at, ended_at,
                               created_at, updated_at
                        FROM interview_sessions
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, limit),
                    )
                rows = cur.fetchall()

            for row in rows:
                sessions.append(self._row_to_domain(row))

            logger.info(f"Found {len(sessions)} interview sessions for user {user_id}")
            return sessions

        except Exception as e:
            logger.error(f"Failed to find interview sessions for user {user_id}: {e}")
            raise

    def save(self, session: InterviewSession) -> None:
        """保存会话

        Args:
            session: InterviewSession 实例
        """
        try:
            questions_json = json.dumps([q.to_payload() for q in session.questions])

            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO interview_sessions (
                        session_id, user_id, company, position, difficulty,
                        total_questions, status, questions, current_question_idx,
                        correct_count, total_score, started_at, ended_at,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, user_id) DO UPDATE SET
                        company = EXCLUDED.company,
                        position = EXCLUDED.position,
                        difficulty = EXCLUDED.difficulty,
                        total_questions = EXCLUDED.total_questions,
                        status = EXCLUDED.status,
                        questions = EXCLUDED.questions,
                        current_question_idx = EXCLUDED.current_question_idx,
                        correct_count = EXCLUDED.correct_count,
                        total_score = EXCLUDED.total_score,
                        started_at = EXCLUDED.started_at,
                        ended_at = EXCLUDED.ended_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        session.session_id,
                        session.user_id,
                        session.company,
                        session.position,
                        session.difficulty.value,
                        session.total_questions,
                        session.status.value,
                        questions_json,
                        session.current_question_idx,
                        session.correct_count,
                        session.total_score,
                        session.started_at,
                        session.ended_at,
                        session.created_at,
                        session.updated_at,
                    ),
                )
                self._client.conn.commit()

            logger.info(f"Saved interview session: {session.session_id}")

        except Exception as e:
            logger.error(f"Failed to save interview session {session.session_id}: {e}")
            self._client.conn.rollback()
            raise

    def delete(self, session_id: str, user_id: str) -> None:
        """删除会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM interview_sessions
                    WHERE session_id = %s AND user_id = %s
                    """,
                    (session_id, user_id),
                )
                self._client.conn.commit()

            logger.info(f"Deleted interview session: {session_id}")

        except Exception as e:
            logger.error(f"Failed to delete interview session {session_id}: {e}")
            self._client.conn.rollback()
            raise

    def update_status(self, session_id: str, user_id: str, status: str) -> None:
        """更新会话状态

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            status: 新状态
        """
        try:
            ended_at = None
            if status == "completed":
                ended_at = datetime.now()

            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE interview_sessions
                    SET status = %s, ended_at = COALESCE(%s, ended_at), updated_at = NOW()
                    WHERE session_id = %s AND user_id = %s
                    """,
                    (status, ended_at, session_id, user_id),
                )
                self._client.conn.commit()

            logger.info(f"Updated interview session status: {session_id} -> {status}")

        except Exception as e:
            logger.error(f"Failed to update interview session status {session_id}: {e}")
            self._client.conn.rollback()
            raise

    def count_by_user(self, user_id: str) -> int:
        """统计用户会话数量

        Args:
            user_id: 用户 ID

        Returns:
            会话数量
        """
        try:
            with self._client.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM interview_sessions WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                count = row[0] if row else 0

            return count

        except Exception as e:
            logger.error(f"Failed to count interview sessions for user {user_id}: {e}")
            raise

    def _row_to_domain(self, row: tuple) -> InterviewSession:
        """将数据库行转换为 InterviewSession 聚合

        Args:
            row: 数据库行

        Returns:
            InterviewSession 聚合
        """
        (
            session_id,
            user_id,
            company,
            position,
            difficulty,
            total_questions,
            status,
            questions_json,
            current_question_idx,
            correct_count,
            total_score,
            started_at,
            ended_at,
            created_at,
            updated_at,
        ) = row

        # 解析 questions JSON
        questions_data = json.loads(questions_json) if questions_json else []
        questions = [InterviewQuestion.from_payload(q) for q in questions_data]

        return InterviewSession(
            session_id=session_id,
            user_id=user_id,
            company=company,
            position=position,
            difficulty=DifficultyLevel(difficulty),
            total_questions=total_questions,
            status=SessionStatus(status),
            questions=questions,
            current_question_idx=current_question_idx,
            correct_count=correct_count,
            total_score=total_score,
            started_at=started_at,
            ended_at=ended_at,
            created_at=created_at,
            updated_at=updated_at,
        )


# 单例获取函数
_interview_session_repository: Optional[PostgresInterviewSessionRepository] = None


def get_interview_session_repository() -> PostgresInterviewSessionRepository:
    """获取 InterviewSession 仓库单例"""
    global _interview_session_repository
    if _interview_session_repository is None:
        _interview_session_repository = PostgresInterviewSessionRepository()
    return _interview_session_repository


__all__ = [
    "PostgresInterviewSessionRepository",
    "get_interview_session_repository",
]