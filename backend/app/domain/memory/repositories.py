"""Memory Domain - Repository Protocol

定义记忆领域的仓库接口（Protocol）。
遵循依赖倒置原则：领域层定义接口，基础设施层实现。
"""

from typing import Protocol

from app.domain.memory.aggregates import Memory, MemoryReference, SessionSummary


class MemoryRepository(Protocol):
    """记忆仓库协议

    定义记忆聚合的持久化接口。
    任何实现了这些方法的类都会被类型检查器识别为 MemoryRepository。

    使用 LangGraph PostgresStore 作为底层存储，
    Namespace 结构：("memory", user_id)
    """

    def find_by_user_id(self, user_id: str) -> Memory | None:
        """根据用户 ID 查找记忆聚合

        Args:
            user_id: 用户唯一标识

        Returns:
            Memory 聚合根，不存在时返回 None
        """
        ...

    def save(self, memory: Memory) -> None:
        """保存记忆聚合

        Args:
            memory: Memory 聚合根
        """
        ...

    def delete(self, user_id: str) -> bool:
        """删除记忆聚合

        Args:
            user_id: 用户唯一标识

        Returns:
            是否成功删除
        """
        ...

    def initialize(self, user_id: str) -> Memory:
        """初始化用户记忆

        创建默认的 MEMORY.md、preferences.md、behaviors.md。

        Args:
            user_id: 用户唯一标识

        Returns:
            新创建的 Memory 聚合根
        """
        ...


class SessionSummaryRepository(Protocol):
    """会话摘要仓库协议

    定义会话摘要的持久化接口。
    使用 PostgreSQL 表存储，支持向量检索。
    """

    def create(self, summary: SessionSummary) -> None:
        """创建会话摘要

        Args:
            summary: SessionSummary 实体
        """
        ...

    def find_by_id(self, summary_id: str) -> SessionSummary | None:
        """根据 ID 查找摘要

        Args:
            summary_id: 摘要唯一标识

        Returns:
            SessionSummary 实体，不存在时返回 None
        """
        ...

    def find_by_conversation_id(self, conversation_id: str) -> list[SessionSummary]:
        """根据对话 ID 查找所有摘要

        Args:
            conversation_id: 对话唯一标识

        Returns:
            摘要列表（按创建时间排序）
        """
        ...

    def delete_by_conversation_id(self, conversation_id: str) -> int:
        """删除对话的所有摘要

        Args:
            conversation_id: 对话唯一标识

        Returns:
            删除的摘要数量
        """
        ...

    def search_by_embedding(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[SessionSummary]:
        """语义检索摘要

        Args:
            user_id: 用户唯一标识
            query_embedding: 查询向量
            top_k: 返回数量

        Returns:
            最相似的摘要列表
        """
        ...

    def get_recent(self, user_id: str, limit: int = 5) -> list[SessionSummary]:
        """获取用户最近的摘要

        Args:
            user_id: 用户唯一标识
            limit: 返回数量

        Returns:
            最近创建的摘要列表
        """
        ...


__all__ = [
    "MemoryRepository",
    "SessionSummaryRepository",
]