"""Chat Application Service - 对话应用服务

提供对话管理的用例编排：
- 创建、查询、更新、删除对话
- 管理消息追加
- 自动生成标题

应用层职责：
- 协调领域对象（Conversation 聚合）
- 调用领域服务（TitleGenerator）
- 发布领域事件
"""

import uuid
from datetime import datetime

from app.domain.chat.aggregates import Conversation
from app.domain.chat.repositories import ConversationRepository
from app.infrastructure.common.logger import logger


class ChatApplicationService:
    """对话应用服务

    用例编排：
    - 创建对话
    - 获取对话列表
    - 获取对话详情（含消息）
    - 更新对话标题
    - 删除对话
    - 追加消息
    - 自动生成标题

    注意：流式对话（Chat Agent）仍由 Chat Agent 处理，
    此服务只管理对话元数据和消息记录。
    """

    def __init__(self, conversation_repo: ConversationRepository):
        self._conversation_repo = conversation_repo

    def create_conversation(
        self,
        user_id: str,
        title: str = "新对话",
    ) -> Conversation:
        """创建新对话

        Args:
            user_id: 用户 ID
            title: 对话标题

        Returns:
            新创建的 Conversation 聚合根
        """
        logger.info(f"Create conversation: user={user_id}, title={title}")

        return self._conversation_repo.create_new(user_id, title)

    def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[Conversation]:
        """获取对话列表（不含消息）

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            对话列表
        """
        logger.info(f"List conversations: user={user_id}, limit={limit}")

        return self._conversation_repo.find_all(user_id, limit)

    def get_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> Conversation | None:
        """获取对话详情（含消息）

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            Conversation 聚合根，不存在时返回 None
        """
        logger.info(f"Get conversation: user={user_id}, conv={conversation_id}")

        return self._conversation_repo.find_by_id(user_id, conversation_id)

    def update_title(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
    ) -> bool:
        """更新对话标题

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            title: 新标题

        Returns:
            是否成功更新
        """
        logger.info(f"Update title: user={user_id}, conv={conversation_id}")

        return self._conversation_repo.update_title(user_id, conversation_id, title)

    def delete_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        """删除对话

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            是否成功删除
        """
        logger.info(f"Delete conversation: user={user_id}, conv={conversation_id}")

        return self._conversation_repo.delete(user_id, conversation_id)

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> str:
        """追加消息

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            role: 消息角色（user/assistant）
            content: 消息内容

        Returns:
            新消息的 ID
        """
        logger.info(f"Add message: user={user_id}, conv={conversation_id}, role={role}")

        message_id = str(uuid.uuid4())

        self._conversation_repo.add_message(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            role=role,
            content=content,
        )

        return message_id

    def generate_title(
        self,
        user_id: str,
        conversation_id: str,
        title_generator: callable,
    ) -> str | None:
        """自动生成标题

        当对话有足够消息且标题为默认值时，使用 AI 生成标题。

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            title_generator: 标题生成器函数

        Returns:
            新标题，不需要生成时返回 None
        """
        conversation = self._conversation_repo.find_by_id(user_id, conversation_id)

        if not conversation:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None

        # 只有标题为"新对话"时才自动生成
        if conversation.title != "新对话":
            logger.info(f"Title already customized: {conversation.title}")
            return None

        # 消息数量不足时不生成
        if conversation.message_count() < 4:
            logger.info(f"Messages count {conversation.message_count()} < 4")
            return None

        # 生成标题（使用聚合中的 messages）
        new_title = title_generator(conversation.messages)

        # 更新标题
        self._conversation_repo.update_title(user_id, conversation_id, new_title)

        logger.info(f"Title generated: {new_title}")
        return new_title


def get_chat_service() -> ChatApplicationService:
    """获取对话应用服务实例"""
    from app.infrastructure.persistence.postgres.conversation_repository import (
        get_conversation_repository,
    )

    repo = get_conversation_repository()
    return ChatApplicationService(repo)


__all__ = [
    "ChatApplicationService",
    "get_chat_service",
]