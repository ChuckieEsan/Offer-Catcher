"""Memory Templates 单元测试

测试默认模板功能：
- MEMORY.md 模板
- preferences.md 模板
- behaviors.md 模板
"""

import pytest

from app.domain.memory.templates import (
    MEMORY_MD_TEMPLATE,
    PREFERENCES_TEMPLATE,
    BEHAVIORS_TEMPLATE,
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)


class TestMemoryTemplates:
    """Memory 模板测试"""

    def test_memory_md_template_content(self):
        """测试 MEMORY.md 模板内容"""
        assert "---" in MEMORY_MD_TEMPLATE
        assert "name: user-memory-{user_id}" in MEMORY_MD_TEMPLATE
        assert "## 偏好概要" in MEMORY_MD_TEMPLATE
        assert "## 行为模式概要" in MEMORY_MD_TEMPLATE
        assert "## 会话历史概要" in MEMORY_MD_TEMPLATE
        assert "## 可用 References" in MEMORY_MD_TEMPLATE

    def test_get_memory_template(self):
        """测试获取用户 MEMORY.md 模板"""
        user_id = "test_user_123"

        template = get_memory_template(user_id)

        assert "user-memory-test_user_123" in template
        assert "## 偏好概要" in template

    def test_preferences_template_content(self):
        """测试 preferences.md 模板内容"""
        assert "# 用户偏好详情" in PREFERENCES_TEMPLATE
        assert "## 响应风格" in PREFERENCES_TEMPLATE
        assert "## 话题偏好" in PREFERENCES_TEMPLATE
        assert "## 反馈历史" in PREFERENCES_TEMPLATE

    def test_get_preferences_template(self):
        """测试获取 preferences.md 模板"""
        template = get_preferences_template()

        assert template == PREFERENCES_TEMPLATE
        assert "# 用户偏好详情" in template

    def test_behaviors_template_content(self):
        """测试 behaviors.md 模板内容"""
        assert "# 用户行为模式详情" in BEHAVIORS_TEMPLATE
        assert "提问序列模式" in BEHAVIORS_TEMPLATE
        assert "关注焦点偏好" in BEHAVIORS_TEMPLATE
        assert "追问风格" in BEHAVIORS_TEMPLATE

    def test_get_behaviors_template(self):
        """测试获取 behaviors.md 模板"""
        template = get_behaviors_template()

        assert template == BEHAVIORS_TEMPLATE
        assert "# 用户行为模式详情" in template

    def test_template_placeholders(self):
        """测试模板占位符"""
        # MEMORY.md 应有 {user_id} 占位符
        assert "{user_id}" in MEMORY_MD_TEMPLATE

        # preferences 和 behaviors 不应有占位符
        assert "{user_id}" not in PREFERENCES_TEMPLATE
        assert "{user_id}" not in BEHAVIORS_TEMPLATE