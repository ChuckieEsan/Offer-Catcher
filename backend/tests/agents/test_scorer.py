"""Scorer Agent 测试 - 使用真实 LLM 服务"""

import pytest

from app.agents.scorer import ScorerAgent, get_scorer_agent, calculate_new_level
from app.models.question import MasteryLevel


class TestCalculateNewLevel:
    """熟练度等级计算测试"""

    def test_level_0_to_1_on_pass(self):
        """LEVEL_0 升到 LEVEL_1"""
        result = calculate_new_level(MasteryLevel.LEVEL_0, 60)
        assert result == MasteryLevel.LEVEL_1

    def test_level_0_stay_on_fail(self):
        """LEVEL_0 保持"""
        result = calculate_new_level(MasteryLevel.LEVEL_0, 59)
        assert result == MasteryLevel.LEVEL_0

    def test_level_0_to_2_direct(self):
        """LEVEL_0 直接升到 LEVEL_2 (分数>=85)"""
        result = calculate_new_level(MasteryLevel.LEVEL_0, 85)
        assert result == MasteryLevel.LEVEL_2

    def test_level_1_to_2_on_excellent(self):
        """LEVEL_1 升到 LEVEL_2"""
        result = calculate_new_level(MasteryLevel.LEVEL_1, 85)
        assert result == MasteryLevel.LEVEL_2

    def test_level_1_stay_on_good(self):
        """LEVEL_1 保持 (60-84)"""
        result = calculate_new_level(MasteryLevel.LEVEL_1, 70)
        assert result == MasteryLevel.LEVEL_1

    def test_level_1_stay_on_fail(self):
        """LEVEL_1 保持 (< 60)"""
        result = calculate_new_level(MasteryLevel.LEVEL_1, 50)
        assert result == MasteryLevel.LEVEL_1

    def test_level_2_always_stay(self):
        """LEVEL_2 始终保持"""
        assert calculate_new_level(MasteryLevel.LEVEL_2, 100) == MasteryLevel.LEVEL_2
        assert calculate_new_level(MasteryLevel.LEVEL_2, 50) == MasteryLevel.LEVEL_2
        assert calculate_new_level(MasteryLevel.LEVEL_2, 0) == MasteryLevel.LEVEL_2


class TestScorerAgent:
    """Scorer Agent 测试类（真实服务）"""

    @pytest.fixture(scope="class")
    def agent(self):
        """创建真实的 Scorer Agent"""
        agent = ScorerAgent(provider="dashscope")
        yield agent

    def test_scorer_initialized(self, agent):
        """测试 Scorer Agent 初始化"""
        assert agent.provider == "dashscope"

    @pytest.mark.asyncio
    async def test_score_with_real_data(self, agent):
        """测试真实评分（需要 Qdrant 中有数据）"""
        # 尝试获取一个已有答案的题目
        from app.infrastructure.persistence.qdrant import get_qdrant_manager
        qdrant_manager = get_qdrant_manager()

        # 搜索有答案的题目
        results = qdrant_manager.search(
            query_vector=[0.0] * 1024,  # 使用零向量，只依赖过滤
            filter_conditions=None,
            limit=50,
            score_threshold=0.0,  # 获取所有结果
        )

        # 找有答案的题目
        questions_with_answer = [r for r in results if r.question_answer]

        if not questions_with_answer:
            pytest.skip("Qdrant 中没有带答案的题目，跳过真实评分测试")

        # 使用第一个有答案的题目
        test_question = questions_with_answer[0]

        # 提交一个模拟答案
        user_answer = "这是一个测试答案，用于验证评分功能是否正常工作。"

        try:
            result = await agent.score(test_question.question_id, user_answer)

            # 验证返回结果
            assert result.question_id == test_question.question_id
            assert result.user_answer == user_answer
            assert 0 <= result.score <= 100
            assert result.mastery_level in [MasteryLevel.LEVEL_0, MasteryLevel.LEVEL_1, MasteryLevel.LEVEL_2]

        except Exception as e:
            pytest.fail(f"评分失败: {e}")

    def test_score_question_not_found(self, agent):
        """测试题目不存在时抛出异常"""
        import asyncio

        # 尝试获取一个不存在的题目 - Qdrant 会抛出异常
        # 由于 ID 格式问题，我们需要捕获这个异常
        try:
            asyncio.run(agent.score("00000000-0000-0000-0000-000000000000", "我的答案"))
            # 如果没有抛异常，测试失败
            assert False, "Expected exception for nonexistent question"
        except Exception as e:
            # 预期会抛出某种异常（可能是 400 错误）
            assert "Question not found" in str(e) or "Bad Request" in str(e) or "not a valid point" in str(e)


class TestScorerAgentSingleton:
    """单例测试"""

    def test_get_scorer_agent_singleton(self):
        """测试单例获取"""
        from app.agents import scorer as scorer_module
        scorer_module._scorer_agent = None

        agent1 = get_scorer_agent()
        agent2 = get_scorer_agent()

        assert agent1 is agent2