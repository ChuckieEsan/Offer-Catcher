"""Extraction Harness - 使用真实 API Judge 评测记忆提取

核心评测：
1. 判断是否应该记忆
2. 判断记忆类型是否正确
3. 判断临时约束是否正确跳过
4. 判断去重是否正确执行

使用真实 LLM API 作为 Judge，替代 mock 评估。
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from .judge_adapter import get_judge_adapter, JudgeAdapter
from .eval_prompts import (
    render_extraction_prompt,
    render_content_prompt,
)


@dataclass
class ExtractionEvalResult:
    """Extraction 评估结果

    包含 Judge LLM 对 Agent 决策的全面评估。
    """

    case_id: str
    scenario_name: str

    # 决策评估
    should_remember_score: int = 0
    should_remember_reason: str = ""
    memory_type_correct: bool = False
    memory_type_expected: str = "none"
    memory_type_actual: str = "none"
    temporary_constraint_detected: bool = False
    temporary_constraint_in_input: bool = False
    dedup_correct: bool = True
    dedup_needed: bool = False
    decision_overall_score: int = 0

    # 内容评估（如果写入了）
    content_completeness: int | None = None
    content_accuracy: int | None = None
    content_structured: int | None = None
    content_noise_free: int | None = None
    content_overall_score: int | None = None
    missing_keywords: list[str] = field(default_factory=list)
    extra_noise: list[str] = field(default_factory=list)

    # 元数据
    tool_calls: list[str] = field(default_factory=list)
    judge_reason: str = ""
    passed: bool = False
    judge_model: str = ""
    error: str | None = None


class ExtractionHarness:
    """Extraction Harness - 评测记忆提取决策

    使用 LLM-as-Judge 评估 Memory Agent 的决策准确性。
    """

    def __init__(
        self,
        judge_provider: str = "openai",
        judge_model: str = "gpt-4o-mini",
        output_dir: Path | None = None,
    ):
        self.judge = get_judge_adapter(
            provider=judge_provider,
            model=judge_model,
        )
        self.judge_model = judge_model
        self.output_dir = output_dir or Path("tests/memory/llm_judge/artifacts")

    async def evaluate_decision(
        self,
        conversation: str,
        existing_memory: dict,
        agent_decision: dict,
    ) -> dict:
        """评估 Agent 决策

        Args:
            conversation: 对话内容
            existing_memory: 已有记忆（preferences/behaviors/summaries）
            agent_decision: Agent 的决策（tool_calls 等）

        Returns:
            Judge 评估结果
        """
        prompt = render_extraction_prompt(
            conversation=conversation,
            existing_preferences=existing_memory.get("preferences", ""),
            existing_behaviors=existing_memory.get("behaviors", ""),
            existing_summaries=existing_memory.get("summaries", ""),
            tool_calls=agent_decision.get("tool_calls", []),
            wrote_preferences=agent_decision.get("wrote_preferences", False),
            wrote_behaviors=agent_decision.get("wrote_behaviors", False),
            wrote_session_summary=agent_decision.get("wrote_session_summary", False),
            only_cursor=agent_decision.get("only_cursor", False),
        )

        result = await self.judge.evaluate(prompt)
        return result

    async def evaluate_content(
        self,
        conversation: str,
        extracted_content: str,
        memory_type: str,
        expected_keywords: list[str] = [],
    ) -> dict:
        """评估提取内容质量"""

        prompt = render_content_prompt(
            conversation=conversation,
            extracted_content=extracted_content,
            memory_type=memory_type,
            expected_keywords=expected_keywords,
        )

        result = await self.judge.evaluate(prompt)
        return result

    async def run_case(
        self,
        scenario,  # EvalScenario
        agent_result: dict,
    ) -> ExtractionEvalResult:
        """运行单个场景评估

        Args:
            scenario: 评估场景定义
            agent_result: Agent 执行结果

        Returns:
            ExtractionEvalResult
        """
        # 格式化对话
        conversation = self._format_conversation(scenario.messages)

        # 格式化已有记忆
        existing_memory = {
            "preferences": scenario.current_preferences or "",
            "behaviors": scenario.current_behaviors or "",
            "summaries": "",  # TODO: 从 memory_context 获取
        }

        # Agent 决策信息
        tool_calls = agent_result.get("tool_calls", [])
        agent_decision = {
            "tool_calls": tool_calls,
            "wrote_preferences": "update_preferences" in tool_calls,
            "wrote_behaviors": "update_behaviors" in tool_calls,
            "wrote_session_summary": "write_session_summary" in tool_calls,
            "only_cursor": len(tool_calls) == 1 and "update_cursor" in tool_calls,
        }

        # 评估决策
        decision_result = await self.evaluate_decision(
            conversation, existing_memory, agent_decision
        )

        # 如果写入了记忆，评估内容质量
        content_result = None
        if not agent_decision["only_cursor"]:
            extracted_content = self._extract_written_content(agent_result)
            memory_type = (
                "preferences" if agent_decision["wrote_preferences"]
                else "behaviors" if agent_decision["wrote_behaviors"]
                else "session_summary"
            )

            if extracted_content:
                content_result = await self.evaluate_content(
                    conversation,
                    extracted_content,
                    memory_type,
                    scenario.expected_content_keywords,
                )

        # 构建结果
        return ExtractionEvalResult(
            case_id=scenario.name,
            scenario_name=scenario.name,
            should_remember_score=decision_result.get("should_remember_score", 0),
            should_remember_reason=decision_result.get("should_remember_reason", ""),
            memory_type_correct=decision_result.get("memory_type_correct", False),
            memory_type_expected=decision_result.get("memory_type_expected", "none"),
            memory_type_actual=decision_result.get("memory_type_actual", "none"),
            temporary_constraint_detected=decision_result.get(
                "temporary_constraint_detected", False
            ),
            temporary_constraint_in_input=decision_result.get(
                "temporary_constraint_in_input", False
            ),
            dedup_correct=decision_result.get("dedup_correct", True),
            dedup_needed=decision_result.get("dedup_needed", False),
            decision_overall_score=decision_result.get("overall_score", 0),
            content_completeness=content_result.get("completeness") if content_result else None,
            content_accuracy=content_result.get("accuracy") if content_result else None,
            content_structured=content_result.get("structured") if content_result else None,
            content_noise_free=content_result.get("noise_free") if content_result else None,
            content_overall_score=content_result.get("overall_score") if content_result else None,
            missing_keywords=content_result.get("missing_keywords", []) if content_result else [],
            extra_noise=content_result.get("extra_noise", []) if content_result else [],
            tool_calls=tool_calls,
            judge_reason=decision_result.get("reason", ""),
            passed=decision_result.get("passed", False)
            and (content_result.get("passed", True) if content_result else True),
            judge_model=self.judge_model,
            error=decision_result.get("error"),
        )

    def _format_conversation(self, messages: list) -> str:
        """格式化对话"""
        lines = []
        for role, content in messages:
            speaker = "用户" if role == "human" else "AI"
            lines.append(f"{speaker}: {content}")
        return "\n".join(lines)

    def _extract_written_content(self, agent_result: dict) -> str:
        """提取写入的内容"""
        tool_calls = agent_result.get("tool_calls_detail", [])
        for name, args in tool_calls:
            if name in ["update_preferences", "update_behaviors"]:
                return args.get("content", "")
            if name == "write_session_summary":
                return args.get("summary", "")
        return ""

    async def run_all_scenarios(
        self,
        scenarios: list,
        agent_runner,  # Agent 执行函数
    ) -> list[ExtractionEvalResult]:
        """运行所有场景评估

        Args:
            scenarios: 评估场景列表
            agent_runner: Agent 执行器（真实 API）

        Returns:
            评估结果列表
        """
        results = []

        for scenario in scenarios:
            try:
                # 执行 Agent（真实 API）
                agent_result = await agent_runner(scenario)

                # Judge 评估
                eval_result = await self.run_case(scenario, agent_result)
                results.append(eval_result)

            except Exception as e:
                results.append(
                    ExtractionEvalResult(
                        case_id=scenario.name,
                        scenario_name=scenario.name,
                        error=str(e),
                        passed=False,
                    )
                )

        return results

    def generate_report(self, results: list[ExtractionEvalResult]) -> str:
        """生成评估报告"""
        passed = sum(1 for r in results if r.passed)
        total = len(results)

        lines = [
            "=" * 70,
            "LLM-as-Judge Extraction 评估报告",
            "=" * 70,
            f"Judge Model: {self.judge_model}",
            f"总计: {passed}/{total} 通过 ({passed / total:.1%})",
            "-" * 70,
        ]

        # 按类别统计
        categories = {}
        for r in results:
            cat = self._get_category(r.scenario_name)
            if cat not in categories:
                categories[cat] = {"passed": 0, "total": 0, "scores": []}
            categories[cat]["total"] += 1
            categories[cat]["scores"].append(r.decision_overall_score)
            if r.passed:
                categories[cat]["passed"] += 1

        lines.append("按类别统计：")
        for cat, stats in sorted(categories.items()):
            rate = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
            lines.append(
                f"  {cat}: {stats['passed']}/{stats['total']} ({rate:.1%}), 平均得分 {avg_score:.1f}"
            )

        # 关键指标
        lines.append("-" * 70)
        lines.append("关键指标：")

        # over_memory_rate
        over_memory = sum(
            1
            for r in results
            if "temporary" in r.scenario_name.lower()
            and not r.temporary_constraint_detected
        )
        temp_total = sum(1 for r in results if "temporary" in r.scenario_name.lower())
        if temp_total > 0:
            lines.append(f"  - over_memory_rate (临时约束误写): {over_memory / temp_total:.1%}")

        # dedup_failure_rate
        dedup_failed = sum(
            1
            for r in results
            if ("duplicate" in r.scenario_name.lower() or "语义" in r.scenario_name)
            and not r.dedup_correct
        )
        dedup_total = sum(
            1
            for r in results
            if "duplicate" in r.scenario_name.lower() or "语义" in r.scenario_name
        )
        if dedup_total > 0:
            lines.append(f"  - dedup_failure_rate: {dedup_failed / dedup_total:.1%}")

        lines.append("-" * 70)
        lines.append("详细结果：")

        for r in results:
            status = "✓" if r.passed else "✗"
            lines.append(f"{status} {r.scenario_name}")
            lines.append(f"    决策得分: {r.decision_overall_score}/5")
            lines.append(f"    类型正确: {r.memory_type_correct}")
            if r.temporary_constraint_in_input:
                lines.append(f"    临时约束检测: {r.temporary_constraint_detected}")
            if r.content_overall_score:
                lines.append(f"    内容得分: {r.content_overall_score}/5")
            if r.error:
                lines.append(f"    错误: {r.error}")
            if not r.passed:
                lines.append(f"    原因: {r.judge_reason}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def _get_category(self, name: str) -> str:
        """获取场景类别"""
        name_lower = name.lower()
        if "preference" in name_lower or "pref" in name_lower:
            return "偏好类"
        elif "temporary" in name_lower:
            return "临时约束类"
        elif "behavior" in name_lower:
            return "行为模式类"
        elif "session" in name_lower or "summary" in name_lower:
            return "会话摘要类"
        elif "private" in name_lower or "skip" in name_lower or "personal" in name_lower:
            return "应跳过类"
        elif "duplicate" in name_lower or "语义" in name_lower:
            return "去重类"
        elif "chat" in name_lower or "vague" in name_lower or "emoji" in name_lower:
            return "应跳过类"
        else:
            return "其他"


# ============================================================================
# Pytest 测试类
# ============================================================================

@pytest.mark.llm_judge
class TestMemoryExtractionLLMJudge:
    """使用 LLM-as-Judge 评测记忆提取"""

    @pytest.fixture
    def harness(self):
        """创建 Extraction Harness"""
        return ExtractionHarness(
            judge_provider="openai",
            judge_model="gpt-4o-mini",
        )

    @pytest.mark.asyncio
    async def test_single_preference_feedback(self, harness):
        """评测：明确的偏好反馈"""
        # 模拟场景和 Agent 结果
        scenario = type(
            "Scenario",
            (),
            {
                "name": "preference_explicit_feedback",
                "messages": [
                    ("human", "回答简洁一点，不要写那么多废话"),
                    ("ai", "明白了，我会简洁回答"),
                ],
                "current_preferences": "",
                "current_behaviors": "",
                "expected_content_keywords": ["简洁"],
            },
        )()

        agent_result = {
            "tool_calls": ["update_preferences", "update_memory_index", "update_cursor"],
            "tool_calls_detail": [
                ("update_preferences", {"content": "偏好简洁回答"}),
                ("update_memory_index", {}),
                ("update_cursor", {}),
            ],
        }

        # Judge 评估
        result = await harness.run_case(scenario, agent_result)

        print(f"\n决策得分: {result.decision_overall_score}/5")
        print(f"类型正确: {result.memory_type_correct}")
        print(f"原因: {result.judge_reason}")

        assert result.decision_overall_score >= 4
        assert result.memory_type_correct

    @pytest.mark.asyncio
    async def test_single_temporary_constraint(self, harness):
        """评测：临时约束不应写入长期记忆（关键测试）"""
        scenario = type(
            "Scenario",
            (),
            {
                "name": "temporary_constraint_single",
                "messages": [
                    ("human", "这道题先简短回答，后面再细讲"),
                    ("ai", "好的，简短版本是..."),
                ],
                "current_preferences": "",
                "current_behaviors": "",
                "expected_content_keywords": [],
            },
        )()

        agent_result = {
            "tool_calls": ["update_cursor"],
            "tool_calls_detail": [("update_cursor", {})],
        }

        result = await harness.run_case(scenario, agent_result)

        print(f"\n决策得分: {result.decision_overall_score}/5")
        print(f"临时约束检测: {result.temporary_constraint_detected}")
        print(f"原因: {result.judge_reason}")

        assert result.temporary_constraint_detected
        assert result.passed

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_all_scenarios_batch(self, harness):
        """批量评测所有场景"""
        # 导入扩充场景
        from tests.memory.test_memory_eval import ALL_SCENARIOS_FULL

        # 模拟 Agent 结果（实际应替换为真实 Agent 执行）
        results = []

        for scenario in ALL_SCENARIOS_FULL[:10]:  # 先测试 10 个
            # 根据预期生成模拟结果
            agent_result = self._generate_mock_agent_result(scenario)

            eval_result = await harness.run_case(scenario, agent_result)
            results.append(eval_result)

        # 输出报告
        report = harness.generate_report(results)
        print(report)

        # 断言通过率 >= 80%
        pass_rate = sum(1 for r in results if r.passed) / len(results)
        assert pass_rate >= 0.8, f"通过率 {pass_rate:.1%} < 80%"

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
                # cursor 最后
                pass

        tool_calls.append("update_cursor")
        tool_calls_detail.append(("update_cursor", {}))

        return {
            "tool_calls": tool_calls,
            "tool_calls_detail": tool_calls_detail,
        }


# ============================================================================
# 手动运行入口
# ============================================================================


async def run_extraction_harness_demo():
    """演示 Extraction Harness"""
    harness = ExtractionHarness(judge_provider="openai")

    # 测试偏好场景
    pref_scenario = type(
        "Scenario",
        (),
        {
            "name": "preference_demo",
            "messages": [
                ("human", "以后都用中文回答我"),
                ("ai", "好的，我会用中文回答"),
            ],
            "current_preferences": "",
            "current_behaviors": "",
            "expected_content_keywords": ["中文"],
        },
    )()

    pref_result = await harness.run_case(
        pref_scenario,
        {"tool_calls": ["update_preferences", "update_memory_index", "update_cursor"]},
    )

    print(f"偏好场景: 决策得分 {pref_result.decision_overall_score}/5")
    print(f"类型正确: {pref_result.memory_type_correct}")

    # 测试临时约束场景
    temp_scenario = type(
        "Scenario",
        (),
        {
            "name": "temporary_demo",
            "messages": [
                ("human", "这次先不要代码，只要结论"),
                ("ai", "好的，只给结论"),
            ],
            "current_preferences": "",
            "current_behaviors": "",
            "expected_content_keywords": [],
        },
    )()

    temp_result = await harness.run_case(
        temp_scenario, {"tool_calls": ["update_cursor"]}
    )

    print(f"\n临时约束场景: 决策得分 {temp_result.decision_overall_score}/5")
    print(f"临时约束检测: {temp_result.temporary_constraint_detected}")


if __name__ == "__main__":
    asyncio.run(run_extraction_harness_demo())


__all__ = [
    "ExtractionEvalResult",
    "ExtractionHarness",
    "TestMemoryExtractionLLMJudge",
]