"""Memory Repository Implementation - PostgresStore

实现 MemoryRepository Protocol，使用 LangGraph PostgresStore 持久化。
"""

from contextlib import contextmanager
from typing import Generator

from langgraph.store.postgres import PostgresStore

from app.domain.memory.aggregates import Memory, MemoryReference
from app.domain.memory.repositories import MemoryRepository
from app.domain.memory.templates import (
    get_behaviors_template,
    get_memory_template,
    get_preferences_template,
)
from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class PostgresMemoryRepository(MemoryRepository):
    """记忆仓库的 PostgresStore 实现

    实现了 MemoryRepository Protocol 的所有方法。
    使用 LangGraph PostgresStore 作为底层存储。

    Namespace 结构：
    - ("memory", user_id) -> MEMORY.md
    - ("memory", user_id, "references") -> preferences, behaviors, skills/{name}
    """

    def __init__(self, store: PostgresStore):
        """初始化仓库

        Args:
            store: PostgresStore 实例（需要在外部管理上下文）
        """
        self._store = store

    def find_by_user_id(self, user_id: str) -> Memory | None:
        """根据用户 ID 查找记忆聚合"""
        namespace = ("memory", user_id)
        item = self._store.get(namespace, "MEMORY.md")

        if not item:
            return None

        content = item.value.get("content", "")

        # 加载 references
        references = self._load_references(user_id)

        return Memory(
            user_id=user_id,
            content=content,
            references=references,
        )

    def save(self, memory: Memory) -> None:
        """保存记忆聚合"""
        namespace = ("memory", memory.user_id)
        self._store.put(namespace, "MEMORY.md", {"content": memory.content})
        logger.info(f"MEMORY.md saved for user {memory.user_id}")

        # 保存 references
        for ref in memory.references:
            self._save_reference(memory.user_id, ref)

    def delete(self, user_id: str) -> bool:
        """删除记忆聚合"""
        namespace = ("memory", user_id)
        # PostgresStore 没有 delete 方法，通过覆盖空内容来删除
        # 实际上 LangGraph Store 会保留历史，这里用空内容标记删除
        self._store.put(namespace, "MEMORY.md", {"content": "", "deleted": True})
        logger.info(f"Memory deleted for user {user_id}")
        return True

    def initialize(self, user_id: str) -> Memory:
        """初始化用户记忆"""
        # 创建 MEMORY.md
        memory_content = get_memory_template(user_id)
        self._store.put(("memory", user_id), "MEMORY.md", {"content": memory_content})

        # 创建 preferences.md
        prefs_content = get_preferences_template()
        self._store.put(("memory", user_id, "references"), "preferences", {"content": prefs_content})

        # 创建 behaviors.md
        behaviors_content = get_behaviors_template()
        self._store.put(("memory", user_id, "references"), "behaviors", {"content": behaviors_content})

        logger.info(f"Memory initialized for user {user_id}")

        return Memory(
            user_id=user_id,
            content=memory_content,
            references=[
                MemoryReference(reference_name="preferences", content=prefs_content),
                MemoryReference(reference_name="behaviors", content=behaviors_content),
            ],
        )

    def _load_references(self, user_id: str) -> list[MemoryReference]:
        """加载所有引用文件"""
        namespace = ("memory", user_id, "references")
        references = []

        # 加载标准引用
        for ref_name in ["preferences", "behaviors"]:
            item = self._store.get(namespace, ref_name)
            if item:
                references.append(
                    MemoryReference(
                        reference_name=ref_name,
                        content=item.value.get("content", ""),
                    )
                )

        return references

    def _save_reference(self, user_id: str, reference: MemoryReference) -> None:
        """保存单个引用文件"""
        namespace = ("memory", user_id, "references")
        self._store.put(namespace, reference.reference_name, {"content": reference.content})
        logger.info(f"Reference '{reference.reference_name}' saved for user {user_id}")

    def read_content(self, user_id: str) -> str | None:
        """读取 MEMORY.md 内容（便捷方法）"""
        namespace = ("memory", user_id)
        item = self._store.get(namespace, "MEMORY.md")
        return item.value.get("content", "") if item else None

    def write_content(self, user_id: str, content: str) -> None:
        """写入 MEMORY.md 内容（便捷方法）"""
        namespace = ("memory", user_id)
        self._store.put(namespace, "MEMORY.md", {"content": content})
        logger.info(f"MEMORY.md written for user {user_id}")

    def read_reference(self, user_id: str, reference_name: str) -> str | None:
        """读取引用文件内容（便捷方法）"""
        namespace = ("memory", user_id, "references")
        item = self._store.get(namespace, reference_name)
        return item.value.get("content", "") if item else None

    def write_reference(self, user_id: str, reference_name: str, content: str) -> None:
        """写入引用文件内容（便捷方法）"""
        namespace = ("memory", user_id, "references")
        self._store.put(namespace, reference_name, {"content": content})
        logger.info(f"Reference '{reference_name}' written for user {user_id}")

    def read_skill(self, user_id: str, skill_name: str) -> str | None:
        """读取 Skill SKILL.md 内容"""
        namespace = ("memory", user_id, "references", "skills", skill_name)
        item = self._store.get(namespace, "SKILL.md")
        return item.value.get("content", "") if item else None

    def write_skill(self, user_id: str, skill_name: str, content: str) -> None:
        """写入 Skill SKILL.md 内容"""
        namespace = ("memory", user_id, "references", "skills", skill_name)
        self._store.put(namespace, "SKILL.md", {"content": content})
        logger.info(f"Skill '{skill_name}' written for user {user_id}")


@contextmanager
def get_memory_repository() -> Generator[PostgresMemoryRepository, None, None]:
    """获取 MemoryRepository 实例（上下文管理器）

    使用 LangGraph PostgresStore 作为底层存储。

    Yields:
        PostgresMemoryRepository 实例
    """
    settings = get_settings()
    db_uri = settings.postgres_url

    with PostgresStore.from_conn_string(db_uri) as store:
        store.setup()
        yield PostgresMemoryRepository(store)


__all__ = [
    "PostgresMemoryRepository",
    "get_memory_repository",
]