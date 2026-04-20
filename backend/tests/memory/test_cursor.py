"""Memory Cursor 单元测试

测试游标管理功能：
- 游标保存和读取
- 游标互斥检查
- 获取游标后的消息
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage

from app.application.agents.memory.cursor import (
    get_cursor_key,
    save_cursor,
    get_cursor,
    has_memory_writes_since,
    get_messages_since_cursor,
)


class TestCursorKey:
    """游标 Key 测试"""

    def test_get_cursor_key(self):
        """测试生成游标 Key"""
        user_id = "user_001"
        conversation_id = "conv_001"

        key = get_cursor_key(user_id, conversation_id)

        assert key == "memory_cursor:user_001:conv_001"

    def test_get_cursor_key_different_users(self):
        """测试不同用户的 Key 不同"""
        key1 = get_cursor_key("user_001", "conv_001")
        key2 = get_cursor_key("user_002", "conv_001")

        assert key1 != key2

    def test_get_cursor_key_different_conversations(self):
        """测试不同对话的 Key 不同"""
        key1 = get_cursor_key("user_001", "conv_001")
        key2 = get_cursor_key("user_001", "conv_002")

        assert key1 != key2


class TestCursorSaveAndGet:
    """游标保存和读取测试"""

    def test_save_cursor(self):
        """测试保存游标"""
        with patch("app.application.agents.memory.cursor.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_redis.return_value = mock_client

            result = save_cursor("user_001", "conv_001", "msg_uuid_001")

            # 验证 Redis set 被调用
            mock_client.set.assert_called_once()
            assert result is None  # save_cursor 不返回值

    def test_get_cursor_exists(self):
        """测试获取存在的游标"""
        with patch("app.application.agents.memory.cursor.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.get.return_value = b"msg_uuid_001"
            mock_redis.return_value = mock_client

            cursor = get_cursor("user_001", "conv_001")

            assert cursor == "msg_uuid_001"

    def test_get_cursor_not_exists(self):
        """测试获取不存在的游标"""
        with patch("app.application.agents.memory.cursor.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.get.return_value = None
            mock_redis.return_value = mock_client

            cursor = get_cursor("user_001", "conv_001")

            assert cursor is None


class TestCursorMutex:
    """游标互斥测试"""

    def test_has_memory_writes_true(self):
        """测试检测到主 Agent 记忆写入"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            AIMessage(content="<memory_write>preferences</memory_write>已更新偏好", id="msg_2"),
        ]

        result = has_memory_writes_since(messages, "msg_1")
        assert result is True

    def test_has_memory_writes_false(self):
        """测试无主 Agent 记忆写入"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            AIMessage(content="普通回复", id="msg_2"),
        ]

        result = has_memory_writes_since(messages, "msg_1")
        assert result is False

    def test_has_memory_writes_no_ai_messages(self):
        """测试只有用户消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            HumanMessage(content="消息2", id="msg_2"),
        ]

        result = has_memory_writes_since(messages, "msg_1")
        assert result is False

    def test_has_memory_writes_cursor_not_found(self):
        """测试游标位置不在消息列表中"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
        ]

        # 游标不存在于消息列表
        result = has_memory_writes_since(messages, "non_existent_uuid")
        assert result is False

    def test_has_memory_writes_multiple_ai_messages(self):
        """测试多条 AI 消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            AIMessage(content="普通回复", id="msg_2"),
            AIMessage(content="<memory_write>behaviors</memory_write>已更新", id="msg_3"),
        ]

        # 游标在 msg_1，检测到 msg_3 有写入标记
        result = has_memory_writes_since(messages, "msg_1")
        assert result is True


class TestGetMessagesSinceCursor:
    """获取游标后消息测试"""

    def test_get_messages_since_cursor(self):
        """测试获取游标后的消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            HumanMessage(content="消息2", id="msg_2"),
            AIMessage(content="回复1", id="msg_3"),
            HumanMessage(content="消息3", id="msg_4"),
        ]

        # 游标在 msg_2
        new_messages = get_messages_since_cursor(messages, "msg_2")

        assert len(new_messages) == 2
        assert new_messages[0].id == "msg_3"
        assert new_messages[1].id == "msg_4"

    def test_get_messages_since_cursor_none(self):
        """测试游标为 None 时返回全部消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            HumanMessage(content="消息2", id="msg_2"),
        ]

        new_messages = get_messages_since_cursor(messages, None)

        assert len(new_messages) == 2
        assert new_messages == messages

    def test_get_messages_since_cursor_not_found(self):
        """测试游标不存在于消息列表"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
        ]

        new_messages = get_messages_since_cursor(messages, "non_existent_uuid")

        # 游标不存在，返回空列表（因为找不到起始位置）
        assert len(new_messages) == 0

    def test_get_messages_since_cursor_last_message(self):
        """测试游标在最后一条消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            AIMessage(content="回复", id="msg_2"),
        ]

        new_messages = get_messages_since_cursor(messages, "msg_2")

        # 游标在最后一条，无新消息
        assert len(new_messages) == 0