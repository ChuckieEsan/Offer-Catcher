"""Chat Agent 工具功能测试

验证 Chat Agent 中的工具是否正常工作：
- search_questions: 向量检索题目
- search_web: Web 搜索
- query_graph: 图数据库查询

注意：只测试工具是否能正常调用，不测试具体返回结果。
"""
import pytest

from app.agents.chat_agent import (
    ChatAgent,
    get_chat_agent,
)
from app.tools.search_question_tool import search_questions
from app.tools.web_search_tool import search_web
from app.tools.query_graph_tool import query_graph
from app.tools.embedding_tool import get_embedding_tool


class TestSearchQuestionsTool:
    """search_questions 工具测试"""

    def test_tool_has_invoke_method(self):
        """测试工具有 invoke 方法"""
        assert hasattr(search_questions, "invoke")
        assert callable(search_questions.invoke)
        print(f"\n✓ 工具名称: {search_questions.name}")
        print(f"✓ 有 invoke 方法: True")

    def test_tool_invoke_returns_string(self):
        """测试工具调用返回字符串"""
        result = search_questions.invoke("Python")
        assert isinstance(result, str)
        print(f"\n✓ 返回类型: {type(result).__name__}")
        print(f"✓ 结果: {result[:100]}...")

    def test_embedding_works(self):
        """测试 embedding 工具是否可用"""
        embedding_tool = get_embedding_tool()
        vector = embedding_tool.embed_text("测试文本")
        assert vector is not None
        assert len(vector) > 0
        print(f"\n✓ Embedding 维度: {len(vector)}")


class TestSearchWebTool:
    """search_web 工具测试"""

    def test_tool_has_invoke_method(self):
        """测试工具有 invoke 方法"""
        assert hasattr(search_web, "invoke")
        assert callable(search_web.invoke)
        print(f"\n✓ 工具名称: {search_web.name}")
        print(f"✓ 有 invoke 方法: True")

    def test_tool_invoke_returns_string(self):
        """测试工具调用返回字符串"""
        result = search_web.invoke("Python 面试题")
        assert isinstance(result, str)
        print(f"\n✓ 返回类型: {type(result).__name__}")
        print(f"✓ 结果: {result[:100]}...")


class TestQueryGraphTool:
    """query_graph 工具测试"""

    def test_tool_has_invoke_method(self):
        """测试工具有 invoke 方法"""
        assert hasattr(query_graph, "invoke")
        assert callable(query_graph.invoke)
        print(f"\n✓ 工具名称: {query_graph.name}")
        print(f"✓ 有 invoke 方法: True")

    def test_tool_invoke_returns_string(self):
        """测试工具调用返回字符串"""
        result = query_graph.invoke("RAG")
        assert isinstance(result, str)
        print(f"\n✓ 返回类型: {type(result).__name__}")
        print(f"✓ 结果: {result[:100]}...")


class TestChatAgent:
    """Chat Agent 集成测试"""

    def test_get_chat_agent_singleton(self):
        """测试单例获取"""
        agent1 = get_chat_agent()
        agent2 = get_chat_agent()
        assert agent1 is agent2
        print(f"\n✓ 单例模式正常")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])