"""Chat Domain - Repository Protocol

定义对话领域的仓库接口（Protocol）。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。
"""

from typing import Protocol

from app.domain.chat.aggregates import Conversation


class ConversationRepository(Protocol):
    """对话仓库协议

    定义对话聚合的持久化接口。
    任何实现了这些方法的类都会被类型检查器识别为 ConversationRepository。
    """

    def find_by_id(self, user_id: str, conversation_id: str) -> Conversation | None:
        """根据 ID 查找对话聚合（含消息）

        Args:
            user_id: 用户 ID（用于多用户隔离）
            conversation_id: 对话 ID

        Returns:
            Conversation 聚合根，不存在时返回 None
        """
        ...

    def find_all(self, user_id: str, limit: int = 50) -> list[Conversation]:
        """获取用户所有对话（不含消息）

        用于列表展示，只返回元数据，不加载消息。

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            对话列表（按更新时间倒序）
        """
        ...

    def save(self, conversation: Conversation) -> None:
        """保存对话聚合

        Args:
            conversation: Conversation 聚合根
        """
        ...

    def delete(self, user_id: str, conversation_id: str) -> bool:
        """删除对话聚合

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            是否成功删除
        """
        ...

    def update_title(self, user_id: str, conversation_id: str, title: str) -> bool:
        """更新对话标题

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            title: 新标题

        Returns:
            是否成功更新
        """
        ...

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
    ) -> None:
        """追加消息到对话

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            message_id: 消息 ID
            role: 消息角色（user/assistant）
            content: 消息内容
        """
        ...

    def create_new(self, user_id: str, title: str) -> Conversation:
        """创建新对话并返回聚合根

        Args:
            user_id: 用户 ID
            title: 对话标题

        Returns:
            新创建的 Conversation 聚合根
        """
        ...


__all__ = [
    "ConversationRepository",
]