"""PostgreSQL 客户端 - 历史对话存储"""

import gzip
import json
import uuid
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config.settings import get_settings
from app.models.schemas import (
    ExtractTask,
    ExtractTaskCreate,
    ExtractTaskListItem,
    ExtractTaskStatus,
    ExtractedInterview,
    QuestionItem,
)
from app.utils.logger import logger
from app.utils.cache import singleton


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

            # 创建面经解析任务表
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

            # 创建任务表索引
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_id
                ON extract_tasks(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_status
                ON extract_tasks(user_id, status)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_extract_tasks_user_updated
                ON extract_tasks(user_id, updated_at DESC)
            """)

            # 创建收藏表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    question_id VARCHAR(36) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, question_id)
                )
            """)

            # 创建收藏表索引
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_id
                ON favorites(user_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_created
                ON favorites(user_id, created_at DESC)
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

    # ========== 面经解析任务操作 ==========

    def create_extract_task(
        self,
        user_id: str,
        create_req: ExtractTaskCreate,
    ) -> ExtractTask:
        """创建面经解析任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        # 处理图片压缩
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
                (
                    task_id,
                    user_id,
                    create_req.source_type,
                    create_req.source_content,
                    source_images_gz,
                    ExtractTaskStatus.PENDING,
                    now,
                    now,
                ),
            )
            self.conn.commit()

        return ExtractTask(
            task_id=task_id,
            user_id=user_id,
            source_type=create_req.source_type,
            source_content=create_req.source_content,
            source_images_gz=create_req.source_images,  # 返回原始数据
            status=ExtractTaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def get_extract_task(
        self,
        task_id: str,
        user_id: str = None,
    ) -> Optional[ExtractTask]:
        """获取单个任务详情"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content, source_images_gz,
                           status, error_message, result, created_at, updated_at
                    FROM extract_tasks
                    WHERE task_id = %s AND user_id = %s
                    """,
                    (task_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT task_id, user_id, source_type, source_content, source_images_gz,
                           status, error_message, result, created_at, updated_at
                    FROM extract_tasks
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
            row = cur.fetchone()

        if not row:
            return None

        return self._row_to_extract_task(row)

    def get_extract_tasks(
        self,
        user_id: str,
        status: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ExtractTaskListItem]:
        """获取任务列表"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    """
                    SELECT task_id, status, source_type, result, created_at, updated_at
                    FROM extract_tasks
                    WHERE user_id = %s AND status = %s
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, status, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT task_id, status, source_type, result, created_at, updated_at
                    FROM extract_tasks
                    WHERE user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
            rows = cur.fetchall()

        items = []
        for row in rows:
            result = row.get("result")
            if result:
                company = result.get("company", "")
                position = result.get("position", "")
                question_count = len(result.get("questions", []))
            else:
                company = ""
                position = ""
                question_count = 0

            items.append(
                ExtractTaskListItem(
                    task_id=row["task_id"],
                    status=row["status"],
                    source_type=row["source_type"],
                    company=company,
                    position=position,
                    question_count=question_count,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return items

    def count_extract_tasks(
        self,
        user_id: str,
        status: str = None,
    ) -> int:
        """统计任务数量"""
        with self.conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM extract_tasks
                    WHERE user_id = %s AND status = %s
                    """,
                    (user_id, status),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM extract_tasks
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
            return cur.fetchone()[0]

    def update_extract_task_status(
        self,
        task_id: str,
        status: str,
        error_message: str = None,
    ) -> bool:
        """更新任务状态"""
        now = datetime.now()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extract_tasks
                SET status = %s, error_message = %s, updated_at = %s
                WHERE task_id = %s
                """,
                (status, error_message, now, task_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def update_extract_task_result(
        self,
        task_id: str,
        result: ExtractedInterview,
    ) -> bool:
        """更新任务解析结果"""
        now = datetime.now()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extract_tasks
                SET result = %s, status = %s, updated_at = %s
                WHERE task_id = %s
                """,
                (json.dumps(result.model_dump()), ExtractTaskStatus.COMPLETED, now, task_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def update_extract_task_edit(
        self,
        task_id: str,
        user_id: str,
        company: str = None,
        position: str = None,
        questions: List[QuestionItem] = None,
    ) -> Optional[ExtractTask]:
        """编辑任务解析结果"""
        # 先获取当前任务
        task = self.get_extract_task(task_id, user_id)
        if not task or not task.result:
            return None

        # 更新字段
        result = task.result.model_copy()
        if company is not None:
            result.company = company
        if position is not None:
            result.position = position
        if questions is not None:
            result.questions = questions

        now = datetime.now()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extract_tasks
                SET result = %s, updated_at = %s
                WHERE task_id = %s AND user_id = %s
                """,
                (json.dumps(result.model_dump()), now, task_id, user_id),
            )
            self.conn.commit()

        return self.get_extract_task(task_id, user_id)

    def delete_extract_task(
        self,
        task_id: str,
        user_id: str,
    ) -> bool:
        """删除任务"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM extract_tasks
                WHERE task_id = %s AND user_id = %s
                """,
                (task_id, user_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def _row_to_extract_task(self, row: dict) -> ExtractTask:
        """将数据库行转换为 ExtractTask 模型"""
        # 解析 gzip 压缩的图片
        source_images_gz = row.get("source_images_gz")
        source_images = None
        if source_images_gz:
            try:
                decompressed = gzip.decompress(source_images_gz).decode()
                source_images = json.loads(decompressed)
            except Exception as e:
                logger.warning(f"Failed to decompress images: {e}")

        # 解析 result
        result = None
        if row.get("result"):
            try:
                result = ExtractedInterview(**row["result"])
            except Exception as e:
                logger.warning(f"Failed to parse result: {e}")

        return ExtractTask(
            task_id=row["task_id"],
            user_id=row["user_id"],
            source_type=row["source_type"],
            source_content=row.get("source_content"),
            source_images_gz=source_images,  # 返回解压后的数据
            status=row["status"],
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=result,
        )

    # ========== 收藏操作 ==========

    def add_favorite(
        self,
        user_id: str,
        question_id: str,
    ) -> str:
        """添加收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID（MD5 hash）

        Returns:
            收藏记录 ID

        Raises:
            ValueError: 已收藏过该题目
        """
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

    def remove_favorite(
        self,
        user_id: str,
        question_id: str,
    ) -> bool:
        """取消收藏

        Args:
            user_id: 用户 ID
            question_id: 题目 ID

        Returns:
            是否成功删除
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM favorites
                WHERE user_id = %s AND question_id = %s
                """,
                (user_id, question_id),
            )
            self.conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info(f"Removed favorite: user={user_id}, question={question_id}")
            return deleted

    def get_favorites(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        """获取收藏列表

        Args:
            user_id: 用户 ID
            limit: 每页数量
            offset: 偏移量

        Returns:
            收藏记录列表（包含 question_id 和 created_at）
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, question_id, created_at
                FROM favorites
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()

        return [
            {
                "id": row["id"],
                "question_id": row["question_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def count_favorites(
        self,
        user_id: str,
    ) -> int:
        """统计收藏数量

        Args:
            user_id: 用户 ID

        Returns:
            收藏总数
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM favorites
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()[0]

    def check_favorites(
        self,
        user_id: str,
        question_ids: List[str],
    ) -> dict[str, bool]:
        """批量检查收藏状态

        Args:
            user_id: 用户 ID
            question_ids: 题目 ID 列表

        Returns:
            question_id -> is_favored 的映射
        """
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

    def close(self):
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


@singleton
def get_postgres_client() -> PostgresClient:
    """获取 PostgreSQL 客户端单例"""
    client = PostgresClient()
    client.init_tables()
    return client


__all__ = [
    "PostgresClient",
    "Conversation",
    "Message",
    "get_postgres_client",
    # ExtractTask
    "ExtractTask",
    "ExtractTaskCreate",
    "ExtractTaskListItem",
    "ExtractTaskStatus",
]