"""Memory Domain 单元测试

测试记忆领域模型的核心功能：
- Memory 聚合根
- MemoryReference 实体
- SessionSummary 实体
"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.domain.memory.aggregates import (
    Memory,
    MemoryReference,
    MemoryStatus,
    SessionSummary,
)


class TestMemoryAggregate:
    """Memory 聚合根测试"""

    def test_create_memory(self):
        """测试创建 Memory 聚合根"""
        user_id = str(uuid4())
        content = "测试 MEMORY.md 内容"

        memory = Memory.create(user_id, content)

        assert memory.user_id == user_id
        assert memory.content == content
        assert memory.status == MemoryStatus.ACTIVE
        assert len(memory.references) == 0
        assert memory.created_at is not None
        assert memory.updated_at is not None

    def test_update_memory_content(self):
        """测试更新 MEMORY.md 内容"""
        memory = Memory.create("user_001", "初始内容")

        memory.update_content("新内容")

        assert memory.content == "新内容"
        assert memory.updated_at > memory.created_at

    def test_add_reference(self):
        """测试添加引用文件"""
        memory = Memory.create("user_001", "MEMORY.md 内容")

        ref = MemoryReference.create("preferences", "偏好内容")
        memory.add_reference(ref)

        assert len(memory.references) == 1
        assert memory.get_reference("preferences") is not None

    def test_add_reference_existing_name(self):
        """测试更新同名引用"""
        memory = Memory.create("user_001", "MEMORY.md 内容")

        memory.add_reference(MemoryReference.create("preferences", "旧内容"))
        memory.add_reference(MemoryReference.create("preferences", "新内容"))

        # 应该只有一条，内容被更新
        assert len(memory.references) == 1
        assert memory.get_reference("preferences").content == "新内容"

    def test_get_reference_not_exists(self):
        """测试获取不存在的引用"""
        memory = Memory.create("user_001", "MEMORY.md 内容")

        ref = memory.get_reference("non_existent")
        assert ref is None

    def test_remove_reference(self):
        """测试删除引用"""
        memory = Memory.create("user_001", "MEMORY.md 内容")

        memory.add_reference(MemoryReference.create("preferences", "内容"))
        result = memory.remove_reference("preferences")

        assert result is True
        assert len(memory.references) == 0

    def test_remove_reference_not_exists(self):
        """测试删除不存在的引用"""
        memory = Memory.create("user_001", "MEMORY.md 内容")

        result = memory.remove_reference("non_existent")
        assert result is False

    def test_to_dict(self):
        """测试转换为字典"""
        memory = Memory.create("user_001", "MEMORY.md 内容")
        memory.add_reference(MemoryReference.create("preferences", "偏好内容"))

        data = memory.to_dict()

        assert data["user_id"] == "user_001"
        assert data["content"] == "MEMORY.md 内容"
        assert data["status"] == "active"
        assert len(data["references"]) == 1


class TestMemoryReference:
    """MemoryReference 实体测试"""

    def test_create_reference(self):
        """测试创建引用"""
        ref = MemoryReference.create("preferences", "偏好内容")

        assert ref.reference_name == "preferences"
        assert ref.content == "偏好内容"
        assert ref.updated_at is not None

    def test_update_reference_content(self):
        """测试更新引用内容"""
        ref = MemoryReference.create("preferences", "旧内容")
        old_time = ref.updated_at

        ref.update_content("新内容")

        assert ref.content == "新内容"
        assert ref.updated_at > old_time


class TestSessionSummary:
    """SessionSummary 实体测试"""

    def test_create_session_summary(self):
        """测试创建会话摘要"""
        summary_id = str(uuid4())
        conversation_id = str(uuid4())
        user_id = str(uuid4())

        summary = SessionSummary.create(
            id=summary_id,
            conversation_id=conversation_id,
            user_id=user_id,
            summary="测试摘要内容",
            embedding=[0.1] * 1024,
        )

        assert summary.id == summary_id
        assert summary.conversation_id == conversation_id
        assert summary.user_id == user_id
        assert summary.summary == "测试摘要内容"
        assert summary.embedding is not None
        assert len(summary.embedding) == 1024

    def test_create_session_summary_without_embedding(self):
        """测试创建不带 embedding 的摘要"""
        summary = SessionSummary.create(
            id=str(uuid4()),
            conversation_id=str(uuid4()),
            user_id=str(uuid4()),
            summary="无向量摘要",
        )

        assert summary.embedding is None

    def test_create_session_summary_with_cursor(self):
        """测试创建带游标的摘要"""
        cursor_uuid = str(uuid4())

        summary = SessionSummary.create(
            id=str(uuid4()),
            conversation_id=str(uuid4()),
            user_id=str(uuid4()),
            summary="带游标摘要",
            message_cursor_uuid=cursor_uuid,
        )

        assert summary.message_cursor_uuid == cursor_uuid


class TestMemoryStatus:
    """MemoryStatus 枚举测试"""

    def test_memory_status_values(self):
        """测试枚举值"""
        assert MemoryStatus.ACTIVE.value == "active"
        assert MemoryStatus.ARCHIVED.value == "archived"