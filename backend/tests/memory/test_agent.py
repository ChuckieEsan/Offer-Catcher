"""Memory Agent 单元测试

测试 Memory Agent 的核心功能：
- Agent 创建
- Agent 执行流程
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage

from app.application.agents.memory.agent import (
    create_memory_agent,
    run_memory_agent,
    PROMPTS_DIR,
)
from app.infrastructure.common.prompt import load_prompt_template


class TestCreateMemoryAgent:
    """创建 Memory Agent 测试"""

    def test_create_memory_agent(self):
        """测试创建 Agent"""
        with patch("app.application.agents.memory.agent.get_llm") as mock_llm:
            mock_llm_instance = MagicMock()
            mock_llm.return_value = mock_llm_instance

            agent = create_memory_agent()

            assert agent is not None
            mock_llm.assert_called_once()

    def test_memory_agent_has_tools(self):
        """测试 Agent 包含所有工具"""
        with patch("app.application.agents.memory.agent.get_llm") as mock_llm:
            mock_llm.return_value = MagicMock()

            # Agent 应该有 5 个工具
            from app.application.agents.memory.agent import MEMORY_AGENT_TOOLS
            assert len(MEMORY_AGENT_TOOLS) == 5


class TestRunMemoryAgent:
    """执行 Memory Agent 测试"""

    @pytest.mark.asyncio
    async def test_run_memory_agent_no_new_messages(self):
        """测试无新消息时跳过"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [
            HumanMessage(content="消息1", id="msg_1"),
        ]

        with patch("app.application.agents.memory.agent.get_cursor") as mock_cursor:
            with patch("app.application.agents.memory.agent.get_messages_since_cursor") as mock_get:
                mock_cursor.return_value = "msg_1"  # 游标在最后一条
                mock_get.return_value = []  # 无新消息

                # 应该直接返回，不调用 Agent
                await run_memory_agent(user_id, conversation_id, messages)

                mock_cursor.assert_called_once()
                mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_memory_agent_mutex_detected(self):
        """测试检测到互斥时跳过"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = [
            HumanMessage(content="记住我喜欢中文", id="msg_1"),
            AIMessage(content="<memory_write>preferences</memory_write>已更新", id="msg_2"),
        ]

        with patch("app.application.agents.memory.agent.get_cursor") as mock_cursor:
            with patch("app.application.agents.memory.agent.has_memory_writes_since") as mock_mutex:
                mock_cursor.return_value = "msg_1"
                mock_mutex.return_value = True  # 检测到互斥

                # 应该直接返回，不调用 Agent
                await run_memory_agent(user_id, conversation_id, messages)

                mock_cursor.assert_called_once()
                mock_mutex.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_memory_agent_exception_handling(self):
        """测试异常处理"""
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        messages = []

        with patch("app.application.agents.memory.agent.get_cursor") as mock_cursor:
            mock_cursor.side_effect = Exception("Redis connection failed")

            # 应该捕获异常并记录日志
            await run_memory_agent(user_id, conversation_id, messages)

            # 不应该抛出异常


class TestMemoryAgentPrompt:
    """Memory Agent Prompt 测试"""

    def test_memory_agent_prompt_exists(self):
        """测试 Prompt 文件存在"""
        prompt_path = PROMPTS_DIR / "memory_agent.md"

        assert prompt_path.exists()

    def test_memory_agent_prompt_content(self):
        """测试 Prompt 内容"""
        prompt = load_prompt_template("memory_agent.md", PROMPTS_DIR)

        assert prompt is not None
        # 检查关键标签
        template = prompt.messages[0].prompt.template
        assert "<role>" in template
        assert "<task>" in template
        assert "<tools>" in template
        assert "<rules>" in template
        assert "<context>" in template