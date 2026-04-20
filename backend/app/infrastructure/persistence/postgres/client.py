"""PostgreSQL 客户端 - 历史对话存储

提供 PostgreSQL 连接和对话/消息/任务/收藏等数据持久化功能。
作为基础设施层持久化组件，为应用层提供关系数据库服务。

功能模块：
- 对话管理（Conversation）
- 消息管理（Message）
- 面经解析任务（ExtractTask）
- 收藏管理（Favorite）
"""

import gzip
import json
import uuid
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger
from app.domain.question.aggregates import ExtractTask, ExtractTaskStatus, ExtractedInterview


# ========== 临时数据模型（后续迁移到 Domain 层） ==========


class Conversation:
    """对话数据模型"""
    def __init__(self, id: str, user_id: str, title: str, created_at: datetime, updated_at: datetime):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at


class Message:
    """消息数据模型"""
    def __init__(self, id: str, conversation_id: str, user_id: str, role: str, content: str, created_at: datetime):
        self.id = id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.role = role
        self.content = content
        self.created_at = created_at


class PostgresClient:
    """PostgreSQL 客户端

    用于历史对话存储，支持：
    - 对话和消息管理
    - 面经解析任务管理
    - 收藏管理

    设计原则：
    - 连接池管理
    - pgvector 向量支持
    - 自动表初始化
    """

    def __init__(self) -> None:
        """初始化 PostgreSQL 客户端"""
        settings = get_settings()
        self._conn = None
        self._host = settings.postgres_host
        self._port = settings.postgres_port
        self._user = settings.postgres_user
        self._password = settings.postgres_password
        self._database = settings.postgres_db

    @property
    def conn(self):
        """获取数据库连接"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
            )
            with self._conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self._conn.commit()
            register_vector(self._conn)
            logger.info(f"PostgresClient connected: {self._host}:{self._port}/{self._database}")
        elif self._conn.closed == 0:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except psycopg2.errors.InFailedSqlTransaction:
                logger.warning("PostgreSQL transaction aborted, rolling back")
                self._conn.rollback()
        return self._conn

    def init_tables(self) -> None:
        """初始化表结构"""
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # 对话表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)

            # 消息表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id VARCHAR(36) PRIMARY KEY,
                    conversation_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            # 索引
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)
            """)

            # 面经解析任务表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS extract_tasks (
                    task_id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    source_type VARCHAR(20) NOT NULL,
                    source_content TEXT,
                    source_images_gz BYTEA,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    result JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_id ON extract_tasks(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_status
                ON extract_tasks(user_id, status)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_updated
                ON extract_tasks(user_id, updated_at DESC)
            """)

            # 收藏表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    question_id VARCHAR(36) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, question_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_created
                ON favorites(user_id, created_at DESC)
            """)

            # 会话摘要表（记忆模块）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id VARCHAR(36) PRIMARY KEY,
                    conversation_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    summary TEXT NOT NULL,
                    embedding vector(1024),
                    message_cursor_uuid VARCHAR(36),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_user_id ON session_summaries(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_conversation_id ON session_summaries(conversation_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_user_created
                ON session_summaries(user_id, created_at DESC)
            """)
            # 向量索引（使用 hnsw）
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_embedding ON session_summaries
                USING hnsw (embedding vector_cosine_ops)
            """)

            self.conn.commit()
            logger.info("PostgreSQL tables initialized")

    # ========== 对话操作（Chat 模块使用） ==========

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[Conversation]:
        """获取指定对话"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            row = cur.fetchone()
        return Conversation(**row) if row else None

    # ========== 消息操作（Chat 模块使用） ==========

    def add_message(self, user_id: str, conversation_id: str, role: str, content: str) -> Message:
        """添加消息"""
        msg_id = str(uuid.uuid4())
        now = datetime.now()

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (id, conversation_id, user_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (msg_id, conversation_id, user_id, role, content, now),
            )
            cur.execute(
                """
                UPDATE conversations SET updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (now, conversation_id, user_id),
            )
            self.conn.commit()

        return Message(
            id=msg_id, conversation_id=conversation_id, user_id=user_id,
            role=role, content=content, created_at=now
        )

    # ========== 面经解析任务操作（Worker 使用） ==========

    def get_extract_task(self, task_id: str) -> Optional[ExtractTask]:
        """获取单个任务详情（Worker 使用）"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT task_id, user_id, source_type, source_content, source_images_gz,
                       status, error_message, result, created_at, updated_at
                FROM extract_tasks WHERE task_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()
        return self._row_to_extract_task(row) if row else None

    def update_extract_task_status(self, task_id: str, status: str, error_message: str = None) -> bool:
        """更新任务状态（Worker 使用）"""
        now = datetime.now()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extract_tasks SET status = %s, error_message = %s, updated_at = %s
                WHERE task_id = %s
                """,
                (status, error_message, now, task_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def update_extract_task_result(self, task_id: str, result: ExtractedInterview) -> bool:
        """更新任务解析结果（Worker 使用）"""
        now = datetime.now()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extract_tasks SET result = %s, status = %s, updated_at = %s
                WHERE task_id = %s
                """,
                (json.dumps(result.model_dump()), ExtractTaskStatus.COMPLETED, now, task_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def _row_to_extract_task(self, row: dict) -> ExtractTask:
        """将数据库行转换为 ExtractTask 模型"""
        source_images_gz = row.get("source_images_gz")
        source_images = None
        if source_images_gz:
            try:
                decompressed = gzip.decompress(source_images_gz).decode()
                source_images = json.loads(decompressed)
            except Exception as e:
                logger.warning(f"Failed to decompress images: {e}")

        result = None
        if row.get("result"):
            try:
                result = ExtractedInterview(**row["result"])
            except Exception as e:
                logger.warning(f"Failed to parse result: {e}")

        return ExtractTask(
            task_id=row["task_id"], user_id=row["user_id"],
            source_type=row["source_type"], source_content=row.get("source_content"),
            source_images=source_images, status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"], extracted_interview=result.model_dump() if result else None,
        )

    def close(self) -> None:
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# 单例获取函数
_postgres_client: Optional[PostgresClient] = None


def get_postgres_client() -> PostgresClient:
    """获取 PostgreSQL 客户端单例"""
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        _postgres_client.init_tables()
    return _postgres_client


__all__ = [
    "PostgresClient",
    "get_postgres_client",
    "Conversation",
    "Message",
]