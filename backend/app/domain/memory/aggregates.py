"""Memory Domain - 聚合根和实体

定义记忆领域的聚合根和实体。

聚合设计：
- Memory 聚合根：管理用户记忆主文档（MEMORY.md）
- MemoryReference 实体：聚合内的引用文件（preferences.md, behaviors.md）
- SessionSummary 实体：会话摘要（独立存储在数据库）

聚合内规则：
- MEMORY.md 是主文档，始终加载
- references 按需加载（preferences, behaviors, skills）
- SessionSummary 通过 conversation_id 关联，CASCADE DELETE
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryStatus(str, Enum):
    """记忆状态"""

    ACTIVE = "active"  # 活跃状态
    ARCHIVED = "archived"  # 已归档


class MemoryReference(BaseModel):
    """记忆引用实体（聚合内）

    MemoryReference 是 Memory 聚合内的实体，表示一个引用文件。
    包括 preferences.md、behaviors.md 和自定义 Skill。

    Attributes:
        reference_name: 引用名称（preferences, behaviors, 或 skill 名称）
        content: 文件内容（Markdown 格式）
        updated_at: 最后更新时间
    """

    reference_name: str = Field(description="引用名称")
    content: str = Field(description="文件内容（Markdown 格式）")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")

    @classmethod
    def create(
        cls,
        reference_name: str,
        content: str,
        updated_at: datetime | None = None,
    ) -> "MemoryReference":
        """创建引用实体"""
        return cls(
            reference_name=reference_name,
            content=content,
            updated_at=updated_at or datetime.now(),
        )

    def update_content(self, new_content: str) -> None:
        """更新内容"""
        self.content = new_content
        self.updated_at = datetime.now()


class Memory(BaseModel):
    """记忆聚合根

    Memory 是记忆领域的聚合根，管理：
    - 用户记忆主文档（MEMORY.md）
    - 聚合内的引用文件列表

    聚合边界规则：
    - MEMORY.md 始终加载，提供概要信息
    - references 按需加载
    - 通过 user_id 隔离不同用户的记忆

    Attributes:
        user_id: 用户唯一标识
        content: MEMORY.md 内容
        status: 记忆状态
        references: 引用文件列表
        created_at: 创建时间
        updated_at: 最后更新时间
    """

    user_id: str = Field(description="用户唯一标识")
    content: str = Field(description="MEMORY.md 内容（Markdown 格式）")
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE, description="记忆状态")
    references: list[MemoryReference] = Field(default_factory=list, description="引用文件列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")

    @classmethod
    def create(cls, user_id: str, content: str) -> "Memory":
        """创建记忆聚合根（工厂方法）

        Args:
            user_id: 用户唯一标识
            content: MEMORY.md 内容

        Returns:
            新创建的 Memory 聚合根
        """
        now = datetime.now()
        return cls(
            user_id=user_id,
            content=content,
            status=MemoryStatus.ACTIVE,
            references=[],
            created_at=now,
            updated_at=now,
        )

    def update_content(self, new_content: str) -> None:
        """更新主文档内容"""
        self.content = new_content
        self._touch()

    def add_reference(self, reference: MemoryReference) -> None:
        """添加引用文件（聚合内操作）"""
        # 检查是否已存在同名引用
        existing = self.get_reference(reference.reference_name)
        if existing:
            # 更新现有引用
            existing.update_content(reference.content)
        else:
            # 添加新引用
            self.references.append(reference)
        self._touch()

    def get_reference(self, reference_name: str) -> Optional[MemoryReference]:
        """获取引用文件"""
        for ref in self.references:
            if ref.reference_name == reference_name:
                return ref
        return None

    def remove_reference(self, reference_name: str) -> bool:
        """移除引用文件"""
        for i, ref in enumerate(self.references):
            if ref.reference_name == reference_name:
                self.references.pop(i)
                self._touch()
                return True
        return False

    def _touch(self) -> None:
        """更新时间戳"""
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典（用于持久化）"""
        return {
            "user_id": self.user_id,
            "content": self.content,
            "status": self.status.value,
            "references": [
                {
                    "reference_name": r.reference_name,
                    "content": r.content,
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in self.references
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SessionSummary(BaseModel):
    """会话摘要实体

    SessionSummary 是对话产生的记忆摘要，用于语义检索历史。
    一个 conversation 可以有多条 summary（每轮有价值的对话都可能产生一条）。

    Attributes:
        id: 摘要唯一标识（UUID）
        conversation_id: 关联对话 ID
        user_id: 用户 ID
        summary: 会话摘要（3句话左右）
        embedding: 语义向量（用于检索）
        message_cursor_uuid: 产生此记忆时的游标位置
        created_at: 创建时间
    """

    id: str = Field(description="摘要唯一标识（UUID）")
    conversation_id: str = Field(description="关联对话 ID")
    user_id: str = Field(description="用户 ID")
    summary: str = Field(description="会话摘要（简洁描述关键内容）")
    embedding: Optional[list[float]] = Field(default=None, description="语义向量")
    message_cursor_uuid: Optional[str] = Field(default=None, description="游标位置")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    @classmethod
    def create(
        cls,
        id: str,
        conversation_id: str,
        user_id: str,
        summary: str,
        embedding: list[float] | None = None,
        message_cursor_uuid: str | None = None,
    ) -> "SessionSummary":
        """创建会话摘要"""
        return cls(
            id=id,
            conversation_id=conversation_id,
            user_id=user_id,
            summary=summary,
            embedding=embedding,
            message_cursor_uuid=message_cursor_uuid,
            created_at=datetime.now(),
        )


__all__ = [
    "MemoryStatus",
    "MemoryReference",
    "Memory",
    "SessionSummary",
]