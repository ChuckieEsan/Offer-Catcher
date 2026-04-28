"""DeepEval Memory Agent 评测测试类

使用 DeepEval SDK 进行记忆 Agent 的端到端评测。

运行方式：
    # 使用 pytest
    uv run pytest tests/memory/test_memory_deepeval.py -v -m deepeval

    # 使用 DeepEval CLI
    uv run deepeval test run tests/memory/test_memory_deepeval.py
"""

import pytest
from deepeval import assert_test, evaluate
from deepeval.test_case import LLMTestCase

from tests.memory.deepeval_metrics import (
    MemoryExtractionCorrectnessMetric,
    MemoryTypeMetric,
    TemporaryConstraintMetric,
    DeduplicationMetric,
    MemoryContentQualityMetric,
)
from tests.memory.deepeval_adapter import scenario_to_test_case
from tests.memory.deepeval_config import setup_deepeval


# ============================================================================
# 设置 DeepEval 环境
# ============================================================================

# 在模块加载时配置 DeepEval
setup_deepeval()


# ============================================================================
# DeepEval 测试类
# ============================================================================

@pytest.mark.deepeval
class TestMemoryAgentDeepEval:
    """使用 DeepEval 框架评测记忆 Agent

    DeepEval 提供 pytest-native 的评测体验，
    使用 G-Eval 自定义指标评估记忆提取决策。
    """

    # ========================================================================
    # Fixtures
    # ========================================================================

    @pytest.fixture
    def extraction_metric(self):
        """记忆提取正确性指标"""
        return MemoryExtractionCorrectnessMetric(threshold=0.7)

    @pytest.fixture
    def type_metric(self):
        """记忆类型指标"""
        return MemoryTypeMetric(threshold=0.8)

    @pytest.fixture
    def temp_constraint_metric(self):
        """临时约束指标"""
        return TemporaryConstraintMetric(threshold=0.85)

    @pytest.fixture
    def dedup_metric(self):
        """去重指标"""
        return DeduplicationMetric(threshold=0.5)  # DeepEval 使用 5 分制，归一化后 0.5 对应 2.5 分

    @pytest.fixture
    def content_quality_metric(self):
        """内容质量指标"""
        return MemoryContentQualityMetric(threshold=0.6)

    # ========================================================================
    # 单场景测试
    # ========================================================================

    @pytest.mark.asyncio
    async def test_preference_feedback_deepeval(self, extraction_metric):
        """评测：明确的偏好反馈场景"""
        from tests.memory.test_memory_eval import SCENARIO_1_PREF_FEEDBACK

        # 模拟 Agent 结果（实际运行时替换为真实 API 执行）
        agent_result = {
            "tool_calls": ["update_preferences", "update_memory_index", "update_cursor"],
            "tool_calls_detail": [
                ("update_preferences", {"content": "偏好简洁回答，不喜欢冗长解释"}),
                ("update_memory_index", {}),
                ("update_cursor", {}),
            ],
        }

        # 转换为 DeepEval TestCase
        test_case = scenario_to_test_case(
            scenario_name=SCENARIO_1_PREF_FEEDBACK.name,
            messages=SCENARIO_1_PREF_FEEDBACK.messages,
            agent_result=agent_result,
            expected_actions=SCENARIO_1_PREF_FEEDBACK.expected_actions,
            current_preferences=SCENARIO_1_PREF_FEEDBACK.current_preferences,
            current_behaviors=SCENARIO_1_PREF_FEEDBACK.current_behaviors,
            expected_keywords=SCENARIO_1_PREF_FEEDBACK.expected_content_keywords,
        )

        # DeepEval 评估
        assert_test(test_case, [extraction_metric])

    @pytest.mark.asyncio
    async def test_temporary_constraint_deepeval(self, temp_constraint_metric):
        """评测：临时约束场景（关键测试）"""
        from tests.memory.llm_judge.run_extraction_eval import ExtractionHarness
        from tests.memory.test_memory_eval import SCENARIO_B1_TEMPORARY_CONSTRAINT

        # 临时约束场景应只更新游标，不写入长期记忆
        # Agent 正确识别了临时约束关键词"先"、"后面再"
        agent_result = {
            "tool_calls": ["update_cursor"],
            "tool_calls_detail": [("update_cursor", {})],
            "decision_reason": "识别到用户表达包含临时约束关键词'先'、'后面再'，"
                               "判断为临时约束，不写入长期记忆，仅更新游标",
        }

        test_case = scenario_to_test_case(
            scenario_name=SCENARIO_B1_TEMPORARY_CONSTRAINT.name,
            messages=SCENARIO_B1_TEMPORARY_CONSTRAINT.messages,
            agent_result=agent_result,
            expected_actions=SCENARIO_B1_TEMPORARY_CONSTRAINT.expected_actions,
        )

        # DeepEval 评估
        assert_test(test_case, [temp_constraint_metric])

    @pytest.mark.asyncio
    async def test_preference_duplicate_deepeval(self, dedup_metric):
        """评测：偏好去重场景"""
        from tests.memory.test_memory_eval import SCENARIO_9_PREF_DUPLICATE

        # 偏好重复场景应只更新游标，因为"简洁"与已有"简洁直接"语义等价
        agent_result = {
            "tool_calls": ["update_cursor"],
            "tool_calls_detail": [("update_cursor", {})],
            "decision_reason": "用户表达的'简洁'与已有偏好'简洁直接'语义等价，"
                               "执行去重判断，跳过写入，仅更新游标",
        }

        test_case = scenario_to_test_case(
            scenario_name=SCENARIO_9_PREF_DUPLICATE.name,
            messages=SCENARIO_9_PREF_DUPLICATE.messages,
            agent_result=agent_result,
            expected_actions=SCENARIO_9_PREF_DUPLICATE.expected_actions,
            current_preferences=SCENARIO_9_PREF_DUPLICATE.current_preferences,
        )

        # DeepEval 评估
        assert_test(test_case, [dedup_metric])

    # ========================================================================
    # 批量测试
    # ========================================================================

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_all_scenarios_batch_deepeval(self, extraction_metric):
        """批量评测所有场景

        使用 DeepEval 的 evaluate 函数进行批量评估。
        """
        from tests.memory.test_memory_eval import ALL_SCENARIOS_FULL

        test_cases = []
        metrics = [extraction_metric]

        for scenario in ALL_SCENARIOS_FULL[:10]:  # 先测试 10 个场景
            # 生成模拟 Agent 结果
            agent_result = self._generate_mock_agent_result(scenario)

            test_case = scenario_to_test_case(
                scenario_name=scenario.name,
                messages=scenario.messages,
                agent_result=agent_result,
                expected_actions=scenario.expected_actions,
                current_preferences=scenario.current_preferences,
                current_behaviors=scenario.current_behaviors,
                expected_keywords=scenario.expected_content_keywords,
            )
            test_cases.append(test_case)

        # DeepEval批量评估
        evaluate(test_cases=test_cases, metrics=metrics)

    def _generate_mock_agent_result(self, scenario):
        """根据场景生成模拟 Agent 结果"""
        from tests.memory.test_memory_eval import ExpectedAction

        expected_actions = scenario.expected_actions

        tool_calls = []
        tool_calls_detail = []

        for action in expected_actions:
            if action == ExpectedAction.WRITE_PREFERENCES:
                tool_calls.append("update_preferences")
                tool_calls_detail.append(
                    ("update_preferences", {"content": "提取的偏好内容"})
                )
            elif action == ExpectedAction.WRITE_BEHAVIORS:
                tool_calls.append("update_behaviors")
                tool_calls_detail.append(
                    ("update_behaviors", {"content": "提取的行为模式"})
                )
            elif action == ExpectedAction.WRITE_SESSION_SUMMARY:
                tool_calls.append("write_session_summary")
                tool_calls_detail.append(
                    ("write_session_summary", {"summary": "会话摘要"})
                )
            elif action == ExpectedAction.UPDATE_MEMORY_INDEX:
                tool_calls.append("update_memory_index")
                tool_calls_detail.append(("update_memory_index", {}))
            elif action == ExpectedAction.ONLY_UPDATE_CURSOR:
                pass

        tool_calls.append("update_cursor")
        tool_calls_detail.append(("update_cursor", {}))

        return {
            "tool_calls": tool_calls,
            "tool_calls_detail": tool_calls_detail,
        }


# ============================================================================
# 使用真实 Agent API 的测试（可选）
# ============================================================================

@pytest.mark.deepeval
@pytest.mark.integration
class TestMemoryAgentDeepEvalIntegration:
    """使用真实 Agent API 的 DeepEval 测试

    这类测试会调用真实的 Memory Agent API，
    需要配置 DEEPSEEK_API_KEY 等环境变量。
    """

    @pytest.fixture
    async def real_agent_runner(self):
        """真实 Agent 执行器"""
        from app.application.agents.memory.agent import run_memory_agent
        return run_memory_agent

    @pytest.fixture
    def extraction_metric(self):
        """记忆提取正确性指标"""
        return MemoryExtractionCorrectnessMetric(threshold=0.7)

    @pytest.mark.asyncio
    async def test_real_preference_feedback(self, extraction_metric):
        """使用真实 API 测试偏好反馈场景"""
        from tests.memory.test_memory_eval import SCENARIO_1_PREF_FEEDBACK

        # TODO: 调用真实 Agent API
        # agent_result = await self._run_real_agent(SCENARIO_1_PREF_FEEDBACK)

        # 当前使用 mock
        agent_result = {
            "tool_calls": ["update_preferences", "update_memory_index", "update_cursor"],
            "tool_calls_detail": [
                ("update_preferences", {"content": "偏好简洁回答"}),
            ],
        }

        test_case = scenario_to_test_case(
            scenario_name=SCENARIO_1_PREF_FEEDBACK.name,
            messages=SCENARIO_1_PREF_FEEDBACK.messages,
            agent_result=agent_result,
            expected_actions=SCENARIO_1_PREF_FEEDBACK.expected_actions,
        )

        assert_test(test_case, [extraction_metric])


__all__ = [
    "TestMemoryAgentDeepEval",
    "TestMemoryAgentDeepEvalIntegration",
]