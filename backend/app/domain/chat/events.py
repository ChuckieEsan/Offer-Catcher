"""Chat Domain - Domain Events

定义对话领域的领域事件。
用于跨聚合通信和最终一致性。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConversationCreated:
    """对话创建事件"""

    conversation_id: str
    user_id: str
    title: str
    occurred_at: datetime


@dataclass
class ConversationEnded:
    """对话结束事件

    对话结束时触发，用于：
    - MemoryAgent 提取会话摘要
    - 更新用户长期记忆
    """

    conversation_id: str
    user_id: str
    message_count: int
    occurred_at: datetime


@dataclass
class TitleGenerated:
    """标题生成事件

    AI 自动生成标题后触发。
    """

    conversation_id: str
    user_id: str
    old_title: str
    new_title: str
    occurred_at: datetime


@dataclass
class MessageAdded:
    """消息追加事件"""

    conversation_id: str
    user_id: str
    message_id: str
    role: str
    content: str
    occurred_at: datetime


__all__ = [
    "ConversationCreated",
    "ConversationEnded",
    "TitleGenerated",
    "MessageAdded",
]