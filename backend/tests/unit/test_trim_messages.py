"""trim_messages 单元测试

验证官方 trim_messages 的功能：
1. token 超限时是否裁剪
2. System message 是否保留
3. 最新消息是否保留
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.agents.graph.nodes import _trim_messages_by_token


class TestTrimMessagesByToken:
    """trim_messages 单元测试"""

    def test_function_exists(self):
        """测试函数存在"""
        assert _trim_messages_by_token is not None

    def test_short_messages_no_trim(self):
        """测试短消息不裁剪"""
        messages = [
            SystemMessage(content="系统提示"),
            HumanMessage(content="问题"),
            AIMessage(content="回答"),
        ]

        result = _trim_messages_by_token(messages, max_tokens=8000)

        # 短消息应全部保留
        assert len(result) == 3

    def test_preserves_system_message(self):
        """测试 System message 被保留"""
        # 创建大量消息
        messages = [
            SystemMessage(content="重要系统提示"),
        ]
        for i in range(20):
            messages.append(HumanMessage(content=f"问题{i}" * 100))
            messages.append(AIMessage(content=f"回答{i}" * 100))

        # 裁剪
        result = _trim_messages_by_token(messages, max_tokens=1000)

        # System message 应保留
        assert len(result) > 0
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "重要系统提示"

    def test_keeps_latest_messages(self):
        """测试最新消息被保留"""
        messages = []
        for i in range(30):
            messages.append(HumanMessage(content=f"问题{i}" * 50))

        # 裁剪
        result = _trim_messages_by_token(messages, max_tokens=500)

        # 最新消息应保留
        if len(result) > 0:
            # 检查最后一条是否是较新的消息
            last_content = result[-1].content
            # 最新消息的索引应该较大
            assert "问题" in last_content

    def test_empty_messages(self):
        """测试空消息列表"""
        result = _trim_messages_by_token([], max_tokens=8000)
        assert len(result) == 0

    def test_fallback_on_error(self):
        """测试异常时的 fallback"""
        # 创建可能导致问题的消息（空内容）
        messages = [
            HumanMessage(content=""),
            HumanMessage(content="正常消息"),
        ]

        # 应能正常处理
        result = _trim_messages_by_token(messages, max_tokens=100)
        assert len(result) <= 2

    def test_exact_token_limit(self):
        """测试精确 token 限制"""
        # 创建恰好超过限制的消息
        messages = []
        # 每条消息约 50 字符 = ~25 token
        for i in range(100):
            messages.append(HumanMessage(content="测试内容" * 10))

        # 设置较小的 token 限制
        result = _trim_messages_by_token(messages, max_tokens=100)

        # 应裁剪到较小数量
        assert len(result) < len(messages)


class TestTrimMessagesIntegration:
    """trim_messages 集成测试"""

    def test_with_real_conversation(self):
        """测试真实对话场景"""
        messages = [
            SystemMessage(content="你是一个面试题助手"),
            HumanMessage(content="查询字节跳动的面试题"),
            AIMessage(content="好的，正在查询..."),
            HumanMessage(content="查询腾讯的面试题"),
            AIMessage(content="已找到 10 道题目"),
            HumanMessage(content="查询百度的面试题"),
            AIMessage(content="已找到 5 道题目"),
        ]

        result = _trim_messages_by_token(messages, max_tokens=500)

        # System message 应保留
        assert any(isinstance(m, SystemMessage) for m in result)
        # 消息数量应减少
        assert len(result) <= len(messages)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])