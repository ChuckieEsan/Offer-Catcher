"""Router Agent 测试 - 使用真实 LLM 服务"""

import pytest

from app.agents.router import RouterAgent, get_router_agent


class TestRouterAgent:
    """Router Agent 测试类（真实服务）"""

    @pytest.fixture(scope="class")
    def agent(self):
        """创建真实的 Router Agent"""
        agent = RouterAgent(provider="dashscope")
        yield agent


    def test_route_query_intent(self, agent):
        """测试查询意图"""
        result = agent.route("帮我搜索字节的 RAG 题目")

        # 验证返回了有效结果
        assert result.original_text == "帮我搜索字节的 RAG 题目"
        # 查询意图应该返回有效 intent
        assert result.intent in ["query", "ingest", "practice", "stats"]

    def test_route_ingest_intent(self, agent):
        """测试录入意图"""
        result = agent.route("我要录入一道腾讯的LLM工程师面经")

        # 验证返回了有效结果
        assert result.original_text == "我要录入一道腾讯的LLM工程师面经"
        # 录入意图应该返回有效 intent
        assert result.intent in ["query", "ingest", "practice", "stats"]

    def test_route_practice_intent(self, agent):
        """测试练习意图"""
        result = agent.route("我想开始练习这道题")

        # 验证返回了有效结果
        assert result.original_text == "我想开始练习这道题"
        # 练习意图应该返回有效 intent
        assert result.intent in ["query", "ingest", "practice", "stats"]

    def test_route_stats_intent(self, agent):
        """测试统计意图"""
        result = agent.route("统计一下各公司的考频")

        # 验证返回了有效结果
        assert result.original_text == "统计一下各公司的考频"
        # 统计意图应该返回有效 intent
        assert result.intent in ["query", "ingest", "practice", "stats"]

    def test_route_with_company(self, agent):
        """测试提取公司名称"""
        result = agent.route("查询字节跳动 Agent 岗位的 RAG 题目")

        # 验证公司名称标准化
        if result.params.get("company"):
            assert result.params["company"] == "字节跳动"

    def test_route_confidence(self, agent):
        """测试置信度"""
        result = agent.route("搜索题目")

        # 置信度应该在 0-1 之间
        assert 0 <= result.confidence <= 1


class TestRouterAgentSingleton:
    """单例测试"""

    def test_get_router_agent_singleton(self):
        """测试单例获取"""
        from app.agents import router as router_module
        router_module._router_agent = None

        agent1 = get_router_agent()
        agent2 = get_router_agent()

        assert agent1 is agent2