"""Conversation Repository - PostgreSQL 实现

实现 ConversationRepository Protocol，基于 PostgreSQL 持久化。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。
"""

import uuid
from datetime import datetime

from app.domain.chat.aggregates import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.domain.chat.repositories import ConversationRepository
from app.infrastructure.persistence.postgres.client import PostgresClient
from app.infrastructure.common.logger import logger


class PostgresConversationRepository:
    """对话仓库的 PostgreSQL 实现

    实现了 ConversationRepository Protocol 的所有方法。

    设计要点：
    - 使用 PostgresClient 进行数据库操作
    - 返回 Domain 聚合根和实体
    - 支持多用户隔离（user_id 参数）
    """

    def __init__(self, client: PostgresClient):
        self._client = client

    def find_by_id(self, user_id: str, conversation_id: str) -> Conversation | None:
        """根据 ID 查找对话聚合（含消息）"""
        # 获取对话元数据
        conv_data = self._client.get_conversation(user_id, conversation_id)
        if not conv_data:
            return None

        # 获取消息列表
        messages_data = self._client.get_messages(user_id, conversation_id)

        # 构建 Domain Message 实体
        messages = [
            Message(
                message_id=m.id,
                role=MessageRole(m.role),
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages_data
        ]

        # 构建 Domain Conversation 聚合根
        return Conversation(
            conversation_id=conv_data.id,
            user_id=conv_data.user_id,
            title=conv_data.title,
            status=ConversationStatus.ACTIVE,
            messages=messages,
            created_at=conv_data.created_at,
            updated_at=conv_data.updated_at,
        )

    def find_all(self, user_id: str, limit: int = 50) -> list[Conversation]:
        """获取用户所有对话（不含消息）"""
        convs_data = self._client.get_conversations(user_id, limit)

        return [
            Conversation(
                conversation_id=c.id,
                user_id=c.user_id,
                title=c.title,
                status=ConversationStatus.ACTIVE,
                messages=[],  # 列表展示不加载消息
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convs_data
        ]

    def save(self, conversation: Conversation) -> None:
        """保存对话聚合"""
        existing = self._client.get_conversation(
            conversation.user_id,
            conversation.conversation_id,
        )

        if existing:
            self._client.update_conversation_title(
                conversation.user_id,
                conversation.conversation_id,
                conversation.title,
            )
            logger.info(f"Conversation updated: {conversation.conversation_id}")
        else:
            self._create_conversation(conversation)
            logger.info(f"Conversation created: {conversation.conversation_id}")

    def _create_conversation(self, conversation: Conversation) -> None:
        """创建新对话记录"""
        now = datetime.now()
        conn = self._client.conn

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    conversation.conversation_id,
                    conversation.user_id,
                    conversation.title,
                    conversation.created_at or now,
                    conversation.updated_at or now,
                ),
            )
            conn.commit()

    def delete(self, user_id: str, conversation_id: str) -> bool:
        """删除对话聚合"""
        return self._client.delete_conversation(user_id, conversation_id)

    def update_title(self, user_id: str, conversation_id: str, title: str) -> bool:
        """更新对话标题"""
        return self._client.update_conversation_title(user_id, conversation_id, title)

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
    ) -> None:
        """追加消息到对话"""
        self._client.add_message(user_id, conversation_id, role, content)

    def create_new(self, user_id: str, title: str = "新对话") -> Conversation:
        """创建新对话并返回聚合根"""
        conversation_id = str(uuid.uuid4())
        now = datetime.now()

        # 创建聚合根
        conversation = Conversation.create(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
        )

        # 保存到数据库
        self._create_conversation(conversation)

        return conversation


def get_conversation_repository() -> PostgresConversationRepository:
    """获取对话仓库实例"""
    from app.infrastructure.persistence.postgres import get_postgres_client

    client = get_postgres_client()
    return PostgresConversationRepository(client)


__all__ = [
    "PostgresConversationRepository",
    "get_conversation_repository",
]