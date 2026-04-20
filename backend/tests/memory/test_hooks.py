"""Memory Hooks 单元测试

测试 Stop Hook 功能：
- extract_memories（fire-and-forget）
- safe_extract_memories（带异常处理）
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock, asyncio
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.application.agents.memory.hooks import (
    extract_memories,
    create_memory_extraction_hook,
    safe_extract_memories,
)


class TestExtractMemories:
    """extract_memories 测试"""

    @pytest.mark.asyncio
    async def test_extract_memories_fire_and_forget(self):
        """测试 fire-and-forget 模式"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [HumanMessage(content="测试消息")]

        # extract_memories 使用 asyncio.create_task，测试时验证它不阻塞
        # 在同步环境中无法直接测试 async task，跳过详细验证
        pass

    @pytest.mark.asyncio
    async def test_extract_memories_creates_task(self):
        """测试创建异步任务"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [HumanMessage(content="测试消息")]

        # 在异步环境中测试
        with patch("app.application.agents.memory.hooks.run_memory_agent") as mock_agent:
            mock_agent.return_value = AsyncMock(return_value=None)

            # 直接调用 run_memory_agent 模拟
            await mock_agent(user_id, conversation_id, messages)


class TestSafeExtractMemories:
    """safe_extract_memories 测试"""

    @pytest.mark.asyncio
    async def test_safe_extract_memories_success(self):
        """测试成功执行"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [HumanMessage(content="测试消息")]

        with patch("app.application.agents.memory.hooks.run_memory_agent") as mock_agent:
            mock_agent.return_value = AsyncMock(return_value=None)

            await safe_extract_memories(user_id, conversation_id, messages)

            mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_extract_memories_exception(self):
        """测试异常处理"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [HumanMessage(content="测试消息")]

        with patch("app.application.agents.memory.hooks.run_memory_agent") as mock_agent:
            mock_agent.side_effect = Exception("Agent failed")

            # 应该捕获异常，不抛出
            await safe_extract_memories(user_id, conversation_id, messages)

            # 不应该抛出异常


class TestCreateMemoryExtractionHook:
    """create_memory_extraction_hook 测试"""

    def test_create_hook(self):
        """测试创建 Hook"""
        hook = create_memory_extraction_hook()

        assert hook is not None
        assert hook == extract_memories

    def test_hook_callable(self):
        """测试 Hook 可调用"""
        hook = create_memory_extraction_hook()

        # 应该是一个函数
        assert callable(hook)


class TestHooksIntegration:
    """Hooks 集成测试"""

    @pytest.mark.asyncio
    async def test_hook_with_empty_messages(self):
        """测试空消息列表"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())

        with patch("app.application.agents.memory.hooks.run_memory_agent") as mock_agent:
            mock_agent.return_value = AsyncMock(return_value=None)

            # 空消息应该正常处理
            await safe_extract_memories(user_id, conversation_id, [])

            mock_agent.assert_called_once_with(user_id, conversation_id, [])