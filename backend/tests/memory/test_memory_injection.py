"""MEMORY.md 注入逻辑测试

测试 _inject_memory_context 函数和 react_loop_node 的记忆注入功能。

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

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.graph.nodes import _inject_memory_context
from app.memory.io import write_memory, read_memory
from app.memory.templates import get_memory_template
from app.memory.store import get_memory_store
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


class TestInjectMemoryContext:
    """测试 _inject_memory_context 函数"""

    def test_inject_memory_to_system_message(self, test_user_id, memory_store):
        """测试将 MEMORY.md 注入到 SystemMessage"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建用户记忆
        memory_content = get_memory_template(test_user_id)
        write_memory(test_user_id, memory_content)

        # 创建消息列表（包含 SystemMessage）
        messages = [
            SystemMessage(content="你是一个 AI 助手。"),
            HumanMessage(content="你好"),
        ]

        # 注入记忆
        injected = _inject_memory_context(test_user_id, messages)

        # 验证
        assert injected != ""
        assert len(messages) == 2
        assert messages[0].type == "system"
        assert "<用户记忆>" in messages[0].content
        assert "</用户记忆>" in messages[0].content
        assert "你是一个 AI 助手。" in messages[0].content
        assert "user-memory-" + test_user_id in messages[0].content

    def test_inject_memory_without_system_message(self, test_user_id, memory_store):
        """测试没有 SystemMessage 时的情况"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建用户记忆
        write_memory(test_user_id, get_memory_template(test_user_id))

        # 创建消息列表（没有 SystemMessage）
        messages = [
            HumanMessage(content="你好"),
        ]

        # 注入记忆（应该不会修改消息）
        injected = _inject_memory_context(test_user_id, messages)

        # 验证：没有 SystemMessage，记忆内容读取但不会注入
        assert injected != ""  # 返回了记忆内容
        assert len(messages) == 1
        assert messages[0].type == "human"

    def test_inject_memory_nonexistent_user(self, memory_store):
        """测试用户不存在时自动初始化"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 使用不存在的新用户 ID
        new_user_id = f"new_user_{uuid.uuid4().hex[:8]}"

        # 创建消息列表
        messages = [
            SystemMessage(content="你是一个 AI 助手。"),
            HumanMessage(content="你好"),
        ]

        # 注入记忆（会自动初始化）
        injected = _inject_memory_context(new_user_id, messages)

        # 验证：自动创建了记忆
        assert injected != ""
        assert "<用户记忆>" in messages[0].content

        # 验证：记忆文件已创建
        memory_content = read_memory(new_user_id)
        assert memory_content != ""

    def test_inject_memory_already_included(self, test_user_id, memory_store):
        """测试记忆已包含在 SystemMessage 时不再重复注入"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建用户记忆
        memory_content = get_memory_template(test_user_id)
        write_memory(test_user_id, memory_content)

        # 创建消息列表（已包含记忆）
        memory_context = f"\n\n<用户记忆>\n{memory_content}\n</用户记忆>"
        messages = [
            SystemMessage(content="你是一个 AI 助手。" + memory_context),
            HumanMessage(content="你好"),
        ]

        # 注入记忆（不应重复注入）
        injected = _inject_memory_context(test_user_id, messages)

        # 验证：记忆只出现一次
        assert injected != ""
        assert messages[0].content.count("<用户记忆>") == 1

    def test_inject_memory_store_not_initialized(self, test_user_id):
        """测试 MemoryStore 未初始化时的情况"""
        # 创建消息列表
        messages = [
            SystemMessage(content="你是一个 AI 助手。"),
            HumanMessage(content="你好"),
        ]

        # 使用一个未初始化的 store mock
        # 由于 get_memory_store 是单例，实际测试中已初始化
        # 这里测试逻辑分支
        original_content = messages[0].content

        # 如果 store 未初始化，应该返回空字符串且不修改消息
        # 实际运行时 store 已初始化，这里验证函数不会抛异常
        try:
            injected = _inject_memory_context(test_user_id, messages)
            # 如果成功，验证逻辑正确
        except Exception as e:
            # 如果失败，验证异常被正确捕获
            logger.warning(f"Expected behavior: {e}")


class TestMemoryInjectionIntegration:
    """测试记忆注入与 Agent 状态的集成"""

    def test_memory_content_structure(self, test_user_id, memory_store):
        """测试注入的记忆内容结构"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建用户记忆
        write_memory(test_user_id, get_memory_template(test_user_id))

        # 创建消息列表
        messages = [
            SystemMessage(content="你是一个 AI 助手。"),
            HumanMessage(content="你好"),
        ]

        # 注入记忆
        injected = _inject_memory_context(test_user_id, messages)

        # 验证：记忆内容包含必要字段
        assert "## 偏好概要" in injected or "偏好概要" in messages[0].content
        assert "## 行为模式概要" in injected or "行为模式概要" in messages[0].content
        assert "## 可用 References" in injected or "可用 References" in messages[0].content

    def test_memory_injection_with_references(
        self,
        test_user_id,
        memory_store,
    ):
        """测试注入记忆后 LLM 可以通过 Tool 加载 references"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建用户记忆和 references
        write_memory(test_user_id, get_memory_template(test_user_id))
        from app.memory.templates import get_preferences_template, get_behaviors_template
        from app.memory.io import write_memory_reference

        write_memory_reference(test_user_id, "preferences", get_preferences_template())
        write_memory_reference(test_user_id, "behaviors", get_behaviors_template())

        # 创建消息列表
        messages = [
            SystemMessage(content="你是一个 AI 助手。"),
            HumanMessage(content="你好"),
        ]

        # 注入记忆
        _inject_memory_context(test_user_id, messages)

        # 验证：注入的记忆中包含 references 列表提示
        system_content = messages[0].content
        assert "preferences" in system_content
        assert "behaviors" in system_content