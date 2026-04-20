"""Memory Service - 记忆应用服务

编排记忆相关用例，调用 Infrastructure 层 Repository。
"""

from app.domain.memory.aggregates import Memory, MemoryReference
from app.infrastructure.persistence.postgres.memory_repository import get_memory_repository
from app.infrastructure.common.logger import logger


class MemoryService:
    """记忆应用服务

    提供记忆相关的用例编排：
    - 获取用户记忆（MEMORY.md）
    - 获取偏好设置（preferences.md）
    - 获取行为模式（behaviors.md）
    """

    def get_memory(self, user_id: str) -> Memory | None:
        """获取用户记忆聚合

        Args:
            user_id: 用户唯一标识

        Returns:
            Memory 聚合根，不存在时返回 None
        """
        with get_memory_repository() as repo:
            memory = repo.find_by_user_id(user_id)
            if not memory:
                # 首次访问，初始化记忆
                memory = repo.initialize(user_id)
                logger.info(f"Memory initialized for user {user_id}")
            return memory

    def get_preferences(self, user_id: str) -> str:
        """获取用户偏好设置

        Args:
            user_id: 用户唯一标识

        Returns:
            preferences.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_reference(user_id, "preferences")
            if not content:
                # 首次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_reference(user_id, "preferences")
            return content or ""

    def get_behaviors(self, user_id: str) -> str:
        """获取用户行为模式

        Args:
            user_id: 用户唯一标识

        Returns:
            behaviors.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_reference(user_id, "behaviors")
            if not content:
                # 首次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_reference(user_id, "behaviors")
            return content or ""

    def get_memory_content(self, user_id: str) -> str:
        """获取 MEMORY.md 主文档内容

        Args:
            user_id: 用户唯一标识

        Returns:
            MEMORY.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_content(user_id)
            if not content:
                # 馍次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_content(user_id)
            return content or ""

    def update_preferences(self, user_id: str, content: str) -> None:
        """更新用户偏好设置

        Args:
            user_id: 用户唯一标识
            content: preferences.md 内容（Markdown 格式）
        """
        with get_memory_repository() as repo:
            # 确保 memory 已初始化
            if not repo.read_content(user_id):
                repo.initialize(user_id)
            repo.write_reference(user_id, "preferences", content)
            logger.info(f"preferences.md updated for user {user_id}")

    def update_behaviors(self, user_id: str, content: str) -> None:
        """更新用户行为模式

        Args:
            user_id: 用户唯一标识
            content: behaviors.md 内容（Markdown 格式）
        """
        with get_memory_repository() as repo:
            # 确保 memory 已初始化
            if not repo.read_content(user_id):
                repo.initialize(user_id)
            repo.write_reference(user_id, "behaviors", content)
            logger.info(f"behaviors.md updated for user {user_id}")


def get_memory_service() -> MemoryService:
    """获取 MemoryService 实例"""
    return MemoryService()


__all__ = [
    "MemoryService",
    "get_memory_service",
]