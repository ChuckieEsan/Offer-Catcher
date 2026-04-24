"""面试领域仓库接口

定义 InterviewSession 仓库的 Protocol，供基础设施层实现。
"""

from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class InterviewSessionRepository(Protocol):
    """面试会话仓库接口

    定义面试会话持久化的核心操作。
    基础设施层（如 PostgreSQL）实现此 Protocol。

    Methods:
        find_by_id: 根据 ID 查找会话
        find_by_user: 查找用户的所有会话
        save: 保存会话
        delete: 删除会话
        update_status: 更新会话状态
    """

    def find_by_id(self, session_id: str, user_id: str) -> Optional["InterviewSession"]:
        """根据 ID 查找会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（用于多租户隔离）

        Returns:
            InterviewSession 实例或 None
        """
        ...

    def find_by_user(
        self,
        user_id: str,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list["InterviewSession"]:
        """查找用户的所有会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            status: 状态过滤（可选）

        Returns:
            InterviewSession 列表
        """
        ...

    def save(self, session: "InterviewSession") -> None:
        """保存会话

        Args:
            session: InterviewSession 实例
        """
        ...

    def delete(self, session_id: str, user_id: str) -> None:
        """删除会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
        """
        ...

    def update_status(self, session_id: str, user_id: str, status: str) -> None:
        """更新会话状态

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            status: 新状态
        """
        ...

    def count_by_user(self, user_id: str) -> int:
        """统计用户会话数量

        Args:
            user_id: 用户 ID

        Returns:
            会话数量
        """
        ...


# 为了 Protocol 类型检查，需要导入 InterviewSession
# 但实际使用时由基础设施层导入具体类
from app.domain.interview.aggregates import InterviewSession


__all__ = ["InterviewSessionRepository"]