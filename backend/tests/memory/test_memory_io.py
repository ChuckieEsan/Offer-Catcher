"""记忆读写接口测试

测试 memory/io.py 的读写接口。

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

from app.memory.io import (
    read_memory,
    write_memory,
    read_memory_reference,
    write_memory_reference,
    delete_memory_reference,
    list_memory_references,
    memory_exists,
)
from app.memory.init import (
    initialize_user_memory,
    ensure_user_memory,
)
from app.memory.templates import (
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)
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


class TestMemoryTemplates:
    """测试模板"""

    def test_get_memory_template(self):
        """测试获取 MEMORY.md 模板"""
        user_id = "test_user_123"
        template = get_memory_template(user_id)

        assert template is not None
        assert "user-memory-test_user_123" in template
        assert "## 偏好概要" in template
        assert "## 行为模式概要" in template
        assert "## 会话历史概要" in template
        assert "## 可用 References" in template

    def test_get_preferences_template(self):
        """测试获取 preferences.md 模板"""
        template = get_preferences_template()

        assert template is not None
        assert "# 用户偏好详情" in template
        assert "## 响应风格" in template
        assert "## 话题偏好" in template
        assert "## 反馈历史" in template

    def test_get_behaviors_template(self):
        """测试获取 behaviors.md 模板"""
        template = get_behaviors_template()

        assert template is not None
        assert "# 用户行为模式详情" in template


class TestMemoryStore:
    """测试 MemoryStore"""

    def test_store_initialized(self, memory_store):
        """测试存储初始化"""
        assert memory_store.initialized is True

    def test_store_context_manager(self, memory_store):
        """测试上下文管理器"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        with memory_store._get_store() as store:
            assert store is not None


class TestMemoryIO:
    """测试读写接口"""

    def test_write_and_read_memory(self, test_user_id, memory_store):
        """测试写入和读取 MEMORY.md"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 写入
        test_content = f"""---
name: user-memory-{test_user_id}
description: 测试记忆文档
---

# 用户记忆

测试内容：{test_user_id}
"""
        write_memory(test_user_id, test_content)

        # 读取
        content = read_memory(test_user_id)
        assert content == test_content
        assert test_user_id in content

    def test_read_memory_not_exists(self, memory_store):
        """测试读取不存在的记忆"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        content = read_memory(f"non_existent_user_{uuid.uuid4().hex[:8]}")
        assert content == ""

    def test_write_and_read_reference(self, test_user_id, memory_store):
        """测试写入和读取 reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 先创建 MEMORY.md（否则 reference 无意义）
        write_memory(test_user_id, get_memory_template(test_user_id))

        # 写入 preferences
        preferences_content = """# 用户偏好详情

## 响应风格
- 语言：中文
"""
        write_memory_reference(test_user_id, "preferences", preferences_content)

        # 读取
        content = read_memory_reference(test_user_id, "preferences")
        assert content == preferences_content
        assert "语言：中文" in content

    def test_write_and_read_skill_reference(self, test_user_id, memory_store):
        """测试写入和读取 Skill reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 先创建 MEMORY.md
        write_memory(test_user_id, get_memory_template(test_user_id))

        # 写入 Skill（注意：LangGraph PostgresStore 不允许命名空间标签包含点号）
        # 所以 SKILL.md 存储为 SKILL
        skill_content = """---
name: interview_tips
description: 面试技巧
---

# 面试技巧

1. 准备充分
2. 自信表达
"""
        # 使用不带点号的 reference_name
        write_memory_reference(
            test_user_id,
            "skills/interview_tips/SKILL",
            skill_content,
        )

        # 读取（使用不带点号的 reference_name）
        content = read_memory_reference(test_user_id, "skills/interview_tips/SKILL")
        assert content == skill_content
        assert "面试技巧" in content

    def test_read_reference_not_exists(self, test_user_id, memory_store):
        """测试读取不存在的 reference"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        content = read_memory_reference(test_user_id, "non_existent_ref")
        assert content == ""

    def test_list_references(self, test_user_id, memory_store):
        """测试列出 references"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 创建记忆和 references
        write_memory(test_user_id, get_memory_template(test_user_id))
        write_memory_reference(test_user_id, "preferences", get_preferences_template())
        write_memory_reference(test_user_id, "behaviors", get_behaviors_template())

        # 列出（返回的键名会被添加 .md 扩展名）
        refs = list_memory_references(test_user_id)
        assert len(refs) >= 2
        # 存储键名不带 .md，但 list_memory_references 返回时会添加 .md
        assert "preferences.md" in refs
        assert "behaviors.md" in refs

    def test_memory_exists(self, test_user_id, memory_store):
        """测试记忆存在检查"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 不存在
        assert memory_exists(f"non_existent_user_{uuid.uuid4().hex[:8]}") is False

        # 写入后存在
        write_memory(test_user_id, get_memory_template(test_user_id))
        assert memory_exists(test_user_id) is True


class TestMemoryInit:
    """测试初始化流程"""

    def test_initialize_user_memory(self, test_user_id, memory_store):
        """测试初始化用户记忆"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 初始化
        result = initialize_user_memory(test_user_id)
        assert result is True

        # 验证 MEMORY.md
        memory_content = read_memory(test_user_id)
        assert memory_content != ""
        assert "user-memory-" + test_user_id in memory_content

        # 验证 preferences.md
        prefs_content = read_memory_reference(test_user_id, "preferences")
        assert prefs_content != ""
        assert "# 用户偏好详情" in prefs_content

        # 验证 behaviors.md
        behaviors_content = read_memory_reference(test_user_id, "behaviors")
        assert behaviors_content != ""
        assert "# 用户行为模式详情" in behaviors_content

    def test_initialize_user_memory_already_exists(self, test_user_id, memory_store):
        """测试已存在的用户记忆初始化"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 先初始化
        initialize_user_memory(test_user_id)

        # 再次初始化（应该返回 False）
        result = initialize_user_memory(test_user_id)
        assert result is False

    def test_ensure_user_memory(self, test_user_id, memory_store):
        """测试确保用户记忆存在"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        # 不存在时初始化
        result = ensure_user_memory(test_user_id)
        assert result is True
        assert memory_exists(test_user_id) is True

        # 已存在时直接返回 True
        result = ensure_user_memory(test_user_id)
        assert result is True


class TestMemoryIsolation:
    """测试多租户隔离"""

    def test_user_memory_isolation(self, memory_store):
        """测试用户记忆隔离"""
        if not memory_store.initialized:
            pytest.skip("MemoryStore not initialized")

        user1 = f"user1_{uuid.uuid4().hex[:8]}"
        user2 = f"user2_{uuid.uuid4().hex[:8]}"

        # 用户1 的记忆
        write_memory(user1, f"User1 Memory Content - {user1}")
        write_memory_reference(user1, "preferences", "User1 Preferences")

        # 用户2 的记忆
        write_memory(user2, f"User2 Memory Content - {user2}")
        write_memory_reference(user2, "preferences", "User2 Preferences")

        # 验证隔离
        memory1 = read_memory(user1)
        memory2 = read_memory(user2)

        assert user1 in memory1
        assert user2 not in memory1
        assert user2 in memory2
        assert user1 not in memory2

        prefs1 = read_memory_reference(user1, "preferences")
        prefs2 = read_memory_reference(user2, "preferences")

        assert prefs1 == "User1 Preferences"
        assert prefs2 == "User2 Preferences"