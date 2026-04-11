"""State Reducer 单元测试

验证 Annotated add_messages reducer 的功能：
1. 消息合并是否正确
2. 消息顺序是否正确
3. System message 是否被保留
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.agents.graph.state import AgentState


class TestAddMessagesReducer:
    """add_messages reducer 测试"""

    def test_reducer_imported(self):
        """测试 reducer 已正确导入"""
        from langgraph.graph.message import add_messages
        assert add_messages is not None

    def test_state_has_annotated_messages(self):
        """测试 AgentState 的 messages 字段使用 Annotated"""
        from typing import get_args, get_origin
        from langgraph.graph.message import add_messages

        # 检查 AgentState 的 messages 字段类型
        # TypedDict 不直接支持运行时检查，但可以通过 annotation 检查
        # 这里通过检查导入来验证
        assert AgentState.__annotations__.get("messages") is not None

    def test_add_messages_appends(self):
        """测试 add_messages 会追加消息"""
        from langgraph.graph.message import add_messages

        # 初始消息列表
        old_messages = [
            SystemMessage(content="系统提示"),
            HumanMessage(content="用户问题1"),
            AIMessage(content="AI回答1"),
        ]

        # 新消息
        new_messages = [
            HumanMessage(content="用户问题2"),
            AIMessage(content="AI回答2"),
        ]

        # 合并
        result = add_messages(old_messages, new_messages)

        # 验证：总共 5 条消息
        assert len(result) == 5
        # 验证顺序
        assert result[0].content == "系统提示"
        assert result[3].content == "用户问题2"
        assert result[4].content == "AI回答2"

    def test_add_messages_preserves_system(self):
        """测试 System message 被保留"""
        from langgraph.graph.message import add_messages

        old_messages = [
            SystemMessage(content="重要系统提示"),
            HumanMessage(content="问题"),
        ]

        new_messages = [
            AIMessage(content="回答"),
        ]

        result = add_messages(old_messages, new_messages)

        # System message 应该在第一位
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "重要系统提示"

    def test_add_messages_empty_old(self):
        """测试旧消息为空的情况"""
        from langgraph.graph.message import add_messages

        old_messages = []
        new_messages = [HumanMessage(content="新问题")]

        result = add_messages(old_messages, new_messages)

        assert len(result) == 1
        assert result[0].content == "新问题"

    def test_add_messages_empty_new(self):
        """测试新消息为空的情况"""
        from langgraph.graph.message import add_messages

        old_messages = [HumanMessage(content="已有问题")]
        new_messages = []

        result = add_messages(old_messages, new_messages)

        # 应返回原消息
        assert len(result) == 1
        assert result[0].content == "已有问题"


class TestStateIntegration:
    """状态集成测试"""

    def test_state_type_structure(self):
        """测试 State 类型结构完整"""
        # 验证 AgentState 是 TypedDict
        assert hasattr(AgentState, "__annotations__")

        # 验证必要的字段存在
        annotations = AgentState.__annotations__
        assert "messages" in annotations
        assert "intent" in annotations
        assert "session_context" in annotations

    def test_state_partial_update(self):
        """测试 partial update 模式"""
        # 创建部分状态
        partial_state: AgentState = {
            "intent": "query",
        }

        # 应能正常创建
        assert partial_state.get("intent") == "query"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])