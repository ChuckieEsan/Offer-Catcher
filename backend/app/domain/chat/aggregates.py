"""Chat Domain - 会话聚合

定义智能对话领域的聚合根和实体。

聚合设计：
- Conversation 聚合根：管理对话会话
- Message 实体：聚合内的消息记录

聚合内规则：
- 消息追加是聚合内操作
- 消息不可修改/删除（对话是历史记录）
- title 可由 AI 自动生成
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.shared.enums import MasteryLevel


class ConversationStatus(str, Enum):
    """对话状态"""

    ACTIVE = "active"  # 进行中
    ENDED = "ended"  # 已结束


class MessageRole(str, Enum):
    """消息角色"""

    USER = "user"  # 用户消息
    ASSISTANT = "assistant"  # AI 回复


class Message(BaseModel):
    """消息实体（聚合内）

    消息是 Conversation 聚合内的实体，不可独立存在。
    消息创建后不可修改，对话是历史记录。
    """

    message_id: str = Field(description="消息唯一标识")
    role: MessageRole = Field(description="消息角色")
    content: str = Field(description="消息内容")
    created_at: datetime = Field(description="创建时间")

    @classmethod
    def create(
        cls,
        message_id: str,
        role: MessageRole,
        content: str,
        created_at: datetime | None = None,
    ) -> "Message":
        """创建消息"""
        return cls(
            message_id=message_id,
            role=role,
            content=content,
            created_at=created_at or datetime.now(),
        )


class Conversation(BaseModel):
    """对话聚合根

    Conversation 是对话领域的聚合根，管理：
    - 对话元数据（标题、状态）
    - 聚合内的消息列表

    聚合边界规则：
    - 所有消息操作必须通过 Conversation 方法
    - 消息创建后不可修改/删除
    - 对话结束时发布领域事件
    """

    conversation_id: str = Field(description="对话唯一标识")
    user_id: str = Field(description="用户 ID")
    title: str = Field(default="新对话", description="对话标题")
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE, description="对话状态")
    messages: list[Message] = Field(default_factory=list, description="消息列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    @classmethod
    def create(
        cls,
        conversation_id: str,
        user_id: str,
        title: str = "新对话",
    ) -> "Conversation":
        """创建新对话（工厂方法）

        Args:
            conversation_id: 对话唯一标识
            user_id: 用户 ID
            title: 对话标题

        Returns:
            新创建的 Conversation 聚合根
        """
        now = datetime.now()
        return cls(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            status=ConversationStatus.ACTIVE,
            messages=[],
            created_at=now,
            updated_at=now,
        )

    def add_message(
        self,
        message_id: str,
        role: MessageRole,
        content: str,
    ) -> Message:
        """追加消息（聚合内操作）

        消息追加是聚合边界内的操作，通过聚合根执行。

        Args:
            message_id: 消息唯一标识
            role: 消息角色
            content: 消息内容

        Returns:
            新创建的 Message 实体
        """
        message = Message.create(
            message_id=message_id,
            role=role,
            content=content,
        )
        self.messages.append(message)
        self._touch()
        return message

    def update_title(self, title: str) -> None:
        """更新标题

        Args:
            title: 新标题
        """
        self.title = title
        self._touch()

    def end(self) -> None:
        """结束对话

        对话结束后状态变为 ENDED，可触发领域事件。
        """
        self.status = ConversationStatus.ENDED
        self._touch()

    def _touch(self) -> None:
        """更新时间戳"""
        self.updated_at = datetime.now()

    def get_last_message(self) -> Optional[Message]:
        """获取最后一条消息"""
        if not self.messages:
            return None
        return self.messages[-1]

    def get_user_messages(self) -> list[Message]:
        """获取所有用户消息"""
        return [m for m in self.messages if m.role == MessageRole.USER]

    def get_assistant_messages(self) -> list[Message]:
        """获取所有 AI 回复"""
        return [m for m in self.messages if m.role == MessageRole.ASSISTANT]

    def message_count(self) -> int:
        """消息数量"""
        return len(self.messages)

    def to_dict(self) -> dict:
        """转换为字典（用于持久化）"""
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status.value,
            "messages": [
                {
                    "message_id": m.message_id,
                    "role": m.role.value,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in self.messages
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


__all__ = [
    "ConversationStatus",
    "MessageRole",
    "Message",
    "Conversation",
]