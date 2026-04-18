"""Chat Domain - 智能对话领域

领域职责：
- 对话会话管理
- 消息记录管理
- 标题自动生成
"""

from app.domain.chat.aggregates import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.domain.chat.repositories import ConversationRepository
from app.domain.chat.events import (
    ConversationCreated,
    ConversationEnded,
    TitleGenerated,
    MessageAdded,
)

__all__ = [
    # Aggregates
    "Conversation",
    "ConversationStatus",
    "Message",
    "MessageRole",
    # Repository Protocol
    "ConversationRepository",
    # Events
    "ConversationCreated",
    "ConversationEnded",
    "TitleGenerated",
    "MessageAdded",
]