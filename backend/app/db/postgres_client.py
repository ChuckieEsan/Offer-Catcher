"""PostgreSQL 客户端 - 历史对话存储"""

import uuid
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config.settings import get_settings
from app.utils.logger import logger


class Conversation:
    """对话数据模型"""
    def __init__(
        self,
        id: str,
        user_id: str,
        title: str,
        created_at: datetime,
        updated_at: datetime,
    ):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at


class Message:
    """消息数据模型"""
    def __init__(
        self,
        id: str,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        created_at: datetime,
    ):
        self.id = id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.role = role
        self.content = content
        self.created_at = created_at


class PostgresClient:
    """PostgreSQL 客户端 - 用于历史对话存储"""

    def __init__(self):
        settings = get_settings()
        self._conn = None
        self.host = settings.postgres_host
        self.port = settings.postgres_port
        self.user = settings.postgres_user
        self.password = settings.postgres_password
        self.database = settings.postgres_db

    @property
    def conn(self):
        """获取数据库连接"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            logger.info(f"PostgreSQL connected: {self.host}:{self.port}/{self.database}")
        elif self._conn.closed == 0:
            # 检查是否有未完成的事务，如果有则 rollback
            try:
                # 尝试执行一个简单查询来检查事务状态
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except psycopg2.errors.InFailedSqlTransaction:
                # 事务已中止，需要 rollback
                logger.warning("PostgreSQL transaction aborted, rolling back")
                self._conn.rollback()
        return self._conn

    def init_tables(self):
        """初始化表结构"""
        with self.conn.cursor() as cur:
            # 创建对话表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)

            # 创建消息表
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

            # 创建索引（PostgreSQL 需要单独创建索引）
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id
                ON conversations(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
                ON messages(conversation_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_user_id
                ON messages(user_id)
            """)

            self.conn.commit()
            logger.info("PostgreSQL tables initialized")

    # ========== 对话操作 ==========

    def create_conversation(
        self,
        user_id: str,
        title: str = "新对话",
    ) -> Conversation:
        """创建新对话"""
        conv_id = str(uuid.uuid4())
        now = datetime.now()

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, title, created_at, updated_at
                """,
                (conv_id, user_id, title, now, now),
            )
            self.conn.commit()

        return Conversation(
            id=conv_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )

    def get_conversations(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[Conversation]:
        """获取用户的所有对话（按更新时间倒序）"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

        return [
            Conversation(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def get_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> Optional[Conversation]:
        """获取指定对话"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            row = cur.fetchone()

        if not row:
            return None

        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_conversation_title(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
    ) -> bool:
        """更新对话标题"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE conversations
                SET title = %s, updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (title, datetime.now(), conversation_id, user_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def delete_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        """删除对话"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM conversations
                WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    # ========== 消息操作 ==========

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> Message:
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

            # 更新对话的更新时间
            cur.execute(
                """
                UPDATE conversations
                SET updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (now, conversation_id, user_id),
            )

            self.conn.commit()

        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(
        self,
        user_id: str,
        conversation_id: str,
    ) -> List[Message]:
        """获取对话的所有消息"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, role, content, created_at
                FROM messages
                WHERE conversation_id = %s AND user_id = %s
                ORDER BY created_at ASC
                """,
                (conversation_id, user_id),
            )
            rows = cur.fetchall()

        return [
            Message(
                id=row["id"],
                conversation_id=row["conversation_id"],
                user_id=row["user_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def close(self):
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# 全局单例
_postgres_client: Optional[PostgresClient] = None


def get_postgres_client() -> PostgresClient:
    """获取 PostgreSQL 客户端单例"""
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        _postgres_client.init_tables()
    return _postgres_client


__all__ = ["PostgresClient", "Conversation", "Message", "get_postgres_client"]