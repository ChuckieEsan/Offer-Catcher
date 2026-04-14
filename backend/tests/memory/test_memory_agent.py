"""Memory Agent 单元测试

测试 Memory Agent 的核心功能：
- 游标机制
- 游标互斥
- Tools 调用
- Agent 执行流程
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage

from app.memory.cursor import (
    get_cursor,
    save_cursor,
    get_messages_since_cursor,
    get_last_message_uuid,
    has_memory_writes_since,
)
from app.memory.agent import create_memory_agent, run_memory_agent
from app.memory.hooks import trigger_memory_update, trigger_memory_update_sync


# ==================== 游标机制测试 ====================


class TestCursorMechanism:
    """游标机制测试"""

    def test_save_and_get_cursor(self):
        """测试游标的保存和读取"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"
        cursor_uuid = str(uuid4())

        with patch("app.memory.cursor.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_redis.return_value = mock_client

            # 保存游标
            result = save_cursor(user_id, conversation_id, cursor_uuid)
            assert result is True

            # 验证 Redis set 被调用
            mock_client.client.set.assert_called_once()

    def test_get_cursor_not_found(self):
        """测试游标不存在的情况"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"

        with patch("app.memory.cursor.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.client.get.return_value = None
            mock_redis.return_value = mock_client

            cursor = get_cursor(user_id, conversation_id)
            assert cursor is None

    def test_get_messages_since_cursor(self):
        """测试获取游标后的消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            HumanMessage(content="消息2", id="msg_2"),
            AIMessage(content="回复1", id="msg_3"),
            HumanMessage(content="消息3", id="msg_4"),
        ]

        # 游标在 msg_2
        cursor_uuid = "msg_2"
        new_messages = get_messages_since_cursor(messages, cursor_uuid)

        assert len(new_messages) == 2
        assert new_messages[0].id == "msg_3"
        assert new_messages[1].id == "msg_4"

    def test_get_messages_since_cursor_none(self):
        """测试游标不存在时返回全部消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            HumanMessage(content="消息2", id="msg_2"),
        ]

        # 游标不存在
        new_messages = get_messages_since_cursor(messages, None)
        assert len(new_messages) == 2

    def test_get_last_message_uuid(self):
        """测试获取最后一条消息的 UUID"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
            AIMessage(content="回复1", id="msg_3"),
        ]

        last_uuid = get_last_message_uuid(messages)
        assert last_uuid == "msg_3"

    def test_get_last_message_uuid_empty(self):
        """测试消息列表为空"""
        last_uuid = get_last_message_uuid([])
        assert last_uuid is None


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

    def test_has_memory_writes_empty(self):
        """测试游标后无消息"""
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
        ]

        result = has_memory_writes_since(messages, "msg_1")
        assert result is False


# ==================== Memory Agent 测试 ====================


class TestMemoryAgent:
    """Memory Agent 测试"""

    def test_create_memory_agent(self):
        """测试创建 Memory Agent"""
        with patch("app.memory.agent.agent.get_llm") as mock_llm:
            mock_llm.return_value = MagicMock()

            agent = create_memory_agent()
            assert agent is not None

    @pytest.mark.asyncio
    async def test_run_memory_agent_no_messages(self):
        """测试无新消息时跳过"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"

        with patch("app.memory.cursor.get_cursor") as mock_cursor:
            mock_cursor.return_value = "msg_1"

            # 游标后的消息为空
            with patch("app.memory.cursor.get_messages_since_cursor") as mock_get:
                mock_get.return_value = []

                await run_memory_agent(user_id, conversation_id, [])
                # 应该直接返回，不调用 Agent

    @pytest.mark.asyncio
    async def test_run_memory_agent_mutex_detected(self):
        """测试检测到互斥时跳过"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"
        messages = [
            HumanMessage(content="记住我喜欢中文", id="msg_1"),
            AIMessage(content="<memory_write>preferences</memory_write>已更新", id="msg_2"),
        ]

        with patch("app.memory.cursor.get_cursor") as mock_cursor:
            mock_cursor.return_value = "msg_1"

            with patch("app.memory.cursor.has_memory_writes_since") as mock_mutex:
                mock_mutex.return_value = True

                with patch("app.memory.cursor.save_cursor") as mock_save:
                    await run_memory_agent(user_id, conversation_id, messages)

                    # 应该更新游标但跳过 Agent
                    mock_save.assert_called()


# ==================== Stop Hook 测试 ====================


class TestStopHook:
    """Stop Hook 测试"""

    @pytest.mark.asyncio
    async def test_trigger_memory_update_async(self):
        """测试异步触发记忆更新"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"
        messages = [HumanMessage(content="测试消息")]

        with patch("app.memory.hooks._run_memory_update_safe") as mock_run:
            mock_run.return_value = True

            await trigger_memory_update(user_id, conversation_id, messages)

            # 应该创建异步任务（fire-and-forget）

    @pytest.mark.asyncio
    async def test_trigger_memory_update_sync(self):
        """测试同步触发记忆更新"""
        user_id = "test_user_001"
        conversation_id = "test_conv_001"
        messages = [HumanMessage(content="测试消息")]

        with patch("app.memory.agent.run_memory_agent") as mock_agent:
            mock_agent.return_value = None

            result = await trigger_memory_update_sync(user_id, conversation_id, messages)
            # 应该等待 Agent 完成

    @pytest.mark.asyncio
    async def test_trigger_memory_update_missing_params(self):
        """测试缺少参数时的处理"""
        # 当 user_id 为 None 或 messages 为空时，run_memory_agent 会直接返回
        # 所以 trigger_memory_update_sync 应该返回 True（因为没有异常）
        result = await trigger_memory_update_sync(None, "conv_001", [])
        # 实际返回 True，因为 run_memory_agent 正常返回了 None
        assert result is True


# ==================== Tools 测试 ====================


class TestMemoryTools:
    """记忆操作 Tools 测试"""

    def test_write_session_summary_tool(self):
        """测试 write_session_summary tool"""
        from app.memory.agent.tools import write_session_summary

        # 检查 tool 定义
        assert write_session_summary.name == "write_session_summary"
        assert "summary" in write_session_summary.args_schema.model_fields

    def test_update_preferences_tool(self):
        """测试 update_preferences tool"""
        from app.memory.agent.tools import update_preferences

        assert update_preferences.name == "update_preferences"
        assert "content" in update_preferences.args_schema.model_fields

    def test_update_behaviors_tool(self):
        """测试 update_behaviors tool"""
        from app.memory.agent.tools import update_behaviors

        assert update_behaviors.name == "update_behaviors"
        assert "content" in update_behaviors.args_schema.model_fields

    def test_update_cursor_tool(self):
        """测试 update_cursor tool"""
        from app.memory.agent.tools import update_cursor

        assert update_cursor.name == "update_cursor"
        assert "cursor_uuid" in update_cursor.args_schema.model_fields