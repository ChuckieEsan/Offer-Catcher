"""PostgreSQL 客户端 - 历史对话存储

提供 PostgreSQL 连接和对话/消息/任务/收藏等数据持久化功能。
作为基础设施层持久化组件，为应用层提供关系数据库服务。

功能模块：
- 对话管理（Conversation）
- 消息管理（Message）
- 面经解析任务（ExtractTask）
- 收藏管理（Favorite）
- 会话摘要（SessionSummary）
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
from app.models import (
    ExtractTask,
    ExtractTaskCreate,
    ExtractTaskListItem,
    ExtractTaskStatus,
    ExtractedInterview,
    QuestionItem,
)
from app.models.chat_session import (
    Conversation,
    Message,
    SessionSummary,
    SessionSummarySearchResult,
    SessionSummaryRecentResult,
)


def _row_to_session_summary(row: dict) -> SessionSummary:
    """将 RealDictCursor 返回的 row 转换为 SessionSummary 实例"""
    data = dict(row)
    if data["embedding"] is not None:
        data["embedding"] = list(data["embedding"])
    return SessionSummary(**data)


class PostgresClient:
    """PostgreSQL 客户端

    用于历史对话存储，支持：
    - 对话和消息管理
    - 面经解析任务管理
    - 收藏管理
    - 会话摘要（含向量检索）

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

            # 会话摘要表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    conversation_id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    summary TEXT NOT NULL,
                    embedding vector(1024),
                    session_type VARCHAR(20) DEFAULT 'chat',
                    metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_user_id ON session_summaries(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_user_created
                ON session_summaries(user_id, created_at DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_summaries_embedding
                ON session_summaries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
            """)

            self.conn.commit()
            logger.info("PostgreSQL tables initialized")

    # ========== 对话操作 ==========

    def create_conversation(self, user_id: str, title: str = "新对话") -> Conversation:
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
            id=conv_id, user_id=user_id, title=title, created_at=now, updated_at=now
        )

    def get_conversations(self, user_id: str, limit: int = 50) -> List[Conversation]:
        """获取用户的所有对话"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations WHERE user_id = %s
                ORDER BY updated_at DESC LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()
        return [Conversation(**row) for row in rows]

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

    def update_conversation_title(self, user_id: str, conversation_id: str, title: str) -> bool:
        """更新对话标题"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE conversations SET title = %s, updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (title, datetime.now(), conversation_id, user_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """删除对话"""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                (conversation_id, user_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    # ========== 消息操作 ==========

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

    def get_messages(self, user_id: str, conversation_id: str) -> List[Message]:
        """获取对话的所有消息"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, conversation_id, user_id, role, content, created_at
                FROM messages WHERE conversation_id = %s AND user_id = %s
                ORDER BY created_at ASC
                """,
                (conversation_id, user_id),
            )
            rows = cur.fetchall()
        return [Message(**row) for row in rows]

    # ========== 面经解析任务操作 ==========

    def create_extract_task(self, user_id: str, create_req: ExtractTaskCreate) -> ExtractTask:
        """创建面经解析任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        source_images_gz = None
        if create_req.source_images:
            images_json = json.dumps(create_req.source_images)
            source_images_gz = gzip.compress(images_json.encode())

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extract_tasks
                (task_id, user_id, source_type, source_content, source_images_gz, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (task_id, user_id, create_req.source_type, create_req.source_content,
                 source_images_gz, ExtractTaskStatus.PENDING, now, now),
            )
            self.conn.commit()

        return ExtractTask(
            task_id=task_id, user_id=user_id, source_type=create_req.source_type,
            source_content=create_req.source_content, source_images_gz=create_req.source_images,
            status=ExtractTaskStatus.PENDING, created_at=now, updated_at=now,
        )

    def get_extract_task(self, task_id: str, user_id: str = None) -> Optional[ExtractTask]:
        """获取单个任务详情"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content, source_images_gz,
                           status, error_message, result, created_at, updated_at
                    FROM extract_tasks WHERE task_id = %s AND user_id = %s
                    """,
                    (task_id, user_id),
                )
            else:
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

    def get_extract_tasks(
        self, user_id: str, status: str = None, limit: int = 20, offset: int = 0
    ) -> List[ExtractTaskListItem]:
        """获取任务列表"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    """
                    SELECT task_id, status, source_type, result, created_at, updated_at
                    FROM extract_tasks WHERE user_id = %s AND status = %s
                    ORDER BY updated_at DESC LIMIT %s OFFSET %s
                    """,
                    (user_id, status, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT task_id, status, source_type, result, created_at, updated_at
                    FROM extract_tasks WHERE user_id = %s
                    ORDER BY updated_at DESC LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
            rows = cur.fetchall()

        items = []
        for row in rows:
            result = row.get("result")
            company = result.get("company", "") if result else ""
            position = result.get("position", "") if result else ""
            question_count = len(result.get("questions", [])) if result else 0

            items.append(ExtractTaskListItem(
                task_id=row["task_id"], status=row["status"], source_type=row["source_type"],
                company=company, position=position, question_count=question_count,
                created_at=row["created_at"], updated_at=row["updated_at"],
            ))
        return items

    def count_extract_tasks(self, user_id: str, status: str = None) -> int:
        """统计任务数量"""
        with self.conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT COUNT(*) FROM extract_tasks WHERE user_id = %s AND status = %s",
                    (user_id, status),
                )
            else:
                cur.execute("SELECT COUNT(*) FROM extract_tasks WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]

    def update_extract_task_status(self, task_id: str, status: str, error_message: str = None) -> bool:
        """更新任务状态"""
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
        """更新任务解析结果"""
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

    def delete_extract_task(self, task_id: str, user_id: str) -> bool:
        """删除任务"""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM extract_tasks WHERE task_id = %s AND user_id = %s",
                (task_id, user_id),
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
            source_images_gz=source_images, status=row["status"],
            error_message=row.get("error_message"), created_at=row["created_at"],
            updated_at=row["updated_at"], result=result,
        )

    # ========== 收藏操作 ==========

    def add_favorite(self, user_id: str, question_id: str) -> str:
        """添加收藏"""
        favorite_id = str(uuid.uuid4())
        now = datetime.now()

        with self.conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO favorites (id, user_id, question_id, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (favorite_id, user_id, question_id, now),
                )
                self.conn.commit()
                logger.info(f"Added favorite: user={user_id}, question={question_id}")
                return favorite_id
            except psycopg2.errors.UniqueViolation:
                self.conn.rollback()
                raise ValueError(f"题目已收藏: {question_id}")

    def remove_favorite(self, user_id: str, question_id: str) -> bool:
        """取消收藏"""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM favorites WHERE user_id = %s AND question_id = %s",
                (user_id, question_id),
            )
            self.conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info(f"Removed favorite: user={user_id}, question={question_id}")
            return deleted

    def get_favorites(self, user_id: str, limit: int = 20, offset: int = 0) -> List[dict]:
        """获取收藏列表"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, question_id, created_at FROM favorites
                WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()
        return [{"id": row["id"], "question_id": row["question_id"], "created_at": row["created_at"]} for row in rows]

    def count_favorites(self, user_id: str) -> int:
        """统计收藏数量"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]

    def check_favorites(self, user_id: str, question_ids: List[str]) -> dict[str, bool]:
        """批量检查收藏状态"""
        if not question_ids:
            return {}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT question_id FROM favorites
                WHERE user_id = %s AND question_id = ANY(%s)
                """,
                (user_id, question_ids),
            )
            favored_ids = {row[0] for row in cur.fetchall()}
        return {qid: qid in favored_ids for qid in question_ids}

    # ========== 会话摘要操作 ==========

    def create_session_summary(
        self, conversation_id: str, user_id: str, summary: str,
        embedding: Optional[List[float]], session_type: str = "chat",
        metadata: Optional[dict] = None,
    ) -> SessionSummary:
        """创建会话摘要"""
        now = datetime.now()

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO session_summaries
                (conversation_id, user_id, summary, embedding, session_type, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING conversation_id, user_id, summary, embedding, session_type, metadata, created_at
                """,
                (conversation_id, user_id, summary, embedding, session_type,
                 json.dumps(metadata) if metadata else None, now),
            )
            row = cur.fetchone()
            self.conn.commit()

        logger.info(f"Session summary created: conversation_id={conversation_id}")
        return _row_to_session_summary(row)

    def get_session_summary(self, conversation_id: str, user_id: str) -> Optional[SessionSummary]:
        """获取会话摘要"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT conversation_id, user_id, summary, embedding, session_type, metadata, created_at
                FROM session_summaries WHERE conversation_id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            row = cur.fetchone()
        return _row_to_session_summary(row) if row else None

    def search_session_summaries(
        self, user_id: str, query_embedding: List[float], top_k: int = 5
    ) -> List[SessionSummarySearchResult]:
        """语义检索会话摘要"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT conversation_id, summary, session_type, metadata,
                       1 - (embedding <=> %s::vector) as similarity
                FROM session_summaries WHERE user_id = %s
                ORDER BY embedding <=> %s::vector LIMIT %s
                """,
                (query_embedding, user_id, query_embedding, top_k),
            )
            rows = cur.fetchall()

        return [
            SessionSummarySearchResult(
                conversation_id=row["conversation_id"], summary=row["summary"],
                session_type=row["session_type"],
                metadata=row["metadata"] if row["metadata"] else None,
                similarity=float(row["similarity"]) if row["similarity"] else 0.0,
            )
            for row in rows
        ]

    def get_recent_session_summaries(
        self, user_id: str, limit: int = 5
    ) -> List[SessionSummaryRecentResult]:
        """获取最近 N 条会话摘要"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT ss.conversation_id, ss.summary, ss.session_type, ss.metadata,
                       c.title, c.created_at
                FROM session_summaries ss
                JOIN conversations c ON ss.conversation_id = c.id
                WHERE ss.user_id = %s ORDER BY c.created_at DESC LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

        return [
            SessionSummaryRecentResult(
                conversation_id=row["conversation_id"], summary=row["summary"],
                session_type=row["session_type"],
                metadata=row["metadata"] if row["metadata"] else None,
                title=row["title"], created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_session_summary(
        self, conversation_id: str, user_id: str, summary: str,
        embedding: Optional[List[float]] = None, metadata: Optional[dict] = None,
    ) -> bool:
        """更新会话摘要"""
        with self.conn.cursor() as cur:
            if embedding is not None:
                cur.execute(
                    """
                    UPDATE session_summaries
                    SET summary = %s, embedding = %s, metadata = %s
                    WHERE conversation_id = %s AND user_id = %s
                    """,
                    (summary, embedding, json.dumps(metadata) if metadata else None,
                     conversation_id, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE session_summaries
                    SET summary = %s, metadata = %s
                    WHERE conversation_id = %s AND user_id = %s
                    """,
                    (summary, json.dumps(metadata) if metadata else None,
                     conversation_id, user_id),
                )
            self.conn.commit()
            updated = cur.rowcount > 0
        if updated:
            logger.info(f"Session summary updated: conversation_id={conversation_id}")
        return updated

    def count_session_summaries(self, user_id: str) -> int:
        """统计用户会话摘要数量"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM session_summaries WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]

    def close(self) -> None:
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# 单例获取函数
_postgres_client: Optional[PostgresClient] = None


def get_postgres_client() -> PostgresClient:
    """获取 PostgreSQL 客户端单例

    Returns:
        PostgresClient 实例
    """
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        _postgres_client.init_tables()
    return _postgres_client


__all__ = [
    "PostgresClient",
    "get_postgres_client",
]