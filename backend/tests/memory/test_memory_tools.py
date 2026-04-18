"""记忆 Tool 测试

测试 memory_tools.py 的 Tool 实现。

注意：测试在 test 数据库中进行，避免影响业务数据。
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

# 设置测试环境变量
os.environ["POSTGRES_DB"] = "offer_catcher_test"

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.tools.memory_tools import (
    load_memory_reference,
    search_session_history,
    load_skill,
    UserContext,
    LoadMemoryReferenceInput,
    SearchSessionHistoryInput,
    LoadSkillInput,
)
from app.memory.io import (
    write_memory,
    write_memory_reference,
)
from app.memory.templates import (
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)
from app.memory.store import get_memory_store
from app.db import get_postgres_client
from app.utils.logger import logger


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_memory_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def memory_store():
    """获取 MemoryStore"""
    store = get_memory_store()
    yield store


@pytest.fixture
def postgres_client():
    """获取 PostgreSQL 客户端"""
    client = get_postgres_client()
    yield client


@pytest.fixture
def mock_runtime(test_user_id):
    """创建 Mock ToolRuntime"""
    user_context = UserContext(user_id=test_user_id)

    class MockRuntime:
        context = user_context

    return MockRuntime()


class TestLoadMemoryReferenceTool:
    """测试 load_memory_reference Tool"""

    def test_load_preferences(self, test_user_id, memory_store, mock_runtime):
        """测试加载 preferences reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建记忆
        write_memory(test_user_id, get_memory_template(test_user_id))
        write_memory_reference(test_user_id, "preferences", get_preferences_template())

        # 直接调用 Tool 函数（绕过 invoke，手动传入 runtime）
        result = load_memory_reference.func(
            reference_name="preferences",
            runtime=mock_runtime,
        )

        assert "# 用户偏好详情" in result
        assert "## 响应风格" in result

    def test_load_behaviors(self, test_user_id, memory_store, mock_runtime):
        """测试加载 behaviors reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建记忆
        write_memory(test_user_id, get_memory_template(test_user_id))
        write_memory_reference(test_user_id, "behaviors", get_behaviors_template())

        # 直接调用 Tool 函数
        result = load_memory_reference.func(
            reference_name="behaviors",
            runtime=mock_runtime,
        )

        assert "# 用户行为模式详情" in result

    def test_load_nonexistent_reference(self, test_user_id, memory_store, mock_runtime):
        """测试加载不存在的 reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 直接调用 Tool 函数
        result = load_memory_reference.func(
            reference_name="nonexistent",
            runtime=mock_runtime,
        )

        assert "未找到" in result


class TestSearchSessionHistoryTool:
    """测试 search_session_history Tool"""

    def test_search_with_results(
        self,
        test_user_id,
        memory_store,
        postgres_client,
        mock_runtime,
    ):
        """测试有结果的语义检索"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建对话和摘要
        conv = postgres_client.create_conversation(test_user_id, "RAG 原理讨论")
        postgres_client.create_session_summary(
            conversation_id=conv.id,
            user_id=test_user_id,
            summary="讨论了向量检索和召回阈值设置。用户追问了如何优化检索效果。",
            embedding=[0.1] * 1024,  # 模拟向量
            session_type="chat",
        )

        # 直接调用 Tool 函数
        result = search_session_history.func(
            query="RAG 检索优化",
            top_k=1,
            runtime=mock_runtime,
        )

        assert "相关会话历史" in result
        assert "RAG 原理讨论" in result or "向量检索" in result

        # 清理
        postgres_client.delete_conversation(test_user_id, conv.id)

    def test_search_empty_results(
        self,
        test_user_id,
        memory_store,
        postgres_client,
        mock_runtime,
    ):
        """测试无结果的语义检索"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 直接调用 Tool 函数（用户没有会话历史）
        result = search_session_history.func(
            query="不存在的主题",
            top_k=5,
            runtime=mock_runtime,
        )

        assert "未找到" in result or result == ""


class TestLoadSkillTool:
    """测试 load_skill Tool"""

    def test_load_existing_skill(self, test_user_id, memory_store, mock_runtime):
        """测试加载已存在的 Skill"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建记忆和 Skill
        write_memory(test_user_id, get_memory_template(test_user_id))
        skill_content = """---
name: interview_tips
description: 面试技巧
---

# 面试技巧

1. 准备充分
2. 自信表达
"""
        write_memory_reference(test_user_id, "skills/interview_tips/SKILL", skill_content)

        # 直接调用 Tool 函数
        result = load_skill.func(
            skill_name="interview_tips",
            runtime=mock_runtime,
        )

        assert "面试技巧" in result

    def test_load_nonexistent_skill(self, test_user_id, memory_store, mock_runtime):
        """测试加载不存在的 Skill"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 直接调用 Tool 函数
        result = load_skill.func(
            skill_name="nonexistent_skill",
            runtime=mock_runtime,
        )

        assert "未找到" in result


class TestToolInputModels:
    """测试 Tool 输入模型"""

    def test_load_memory_reference_input(self):
        """测试 LoadMemoryReferenceInput 模型"""
        # 正常输入
        input1 = LoadMemoryReferenceInput(reference_name="preferences")
        assert input1.reference_name == "preferences"

    def test_search_session_history_input(self):
        """测试 SearchSessionHistoryInput 模型"""
        # 正常输入
        input1 = SearchSessionHistoryInput(query="RAG 原理", top_k=5)
        assert input1.query == "RAG 原理"
        assert input1.top_k == 5

        # 默认值
        input2 = SearchSessionHistoryInput(query="测试")
        assert input2.top_k == 3

    def test_load_skill_input(self):
        """测试 LoadSkillInput 模型"""
        input1 = LoadSkillInput(skill_name="interview_tips")
        assert input1.skill_name == "interview_tips"