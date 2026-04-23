"""Memory Agent 评估测试框架

测试 Memory Agent 的决策准确性：
1. 分类准确性：能否正确区分 preferences/behaviors/session_summary
2. 质量判断：能否正确判断值得记忆 vs 不值得记忆
3. 负向反馈处理
4. 去重和合并策略
5. 工具调用顺序

使用真实 LLM 执行 Agent，并评估其输出是否符合预期。

运行方式：
    # 运行所有评估测试
    uv run pytest tests/memory/test_memory_eval.py -v -m eval

    # 只运行特定场景
    uv run pytest tests/memory/test_memory_eval.py::TestMemoryAgentEvaluation::test_scenario_1_preference_feedback -v -m eval
"""

import uuid
from typing import Any
from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from langchain_core.messages import HumanMessage, AIMessage


# ============================================================================
# 评估场景定义
# ============================================================================


class ExpectedAction(Enum):
    """预期的 Agent 行为"""
    WRITE_PREFERENCES = "write_preferences"
    WRITE_BEHAVIORS = "write_behaviors"
    WRITE_SESSION_SUMMARY = "write_session_summary"
    ONLY_UPDATE_CURSOR = "only_update_cursor"  # 不写任何记忆
    UPDATE_MEMORY_INDEX = "update_memory_index"  # 需要更新索引


@dataclass
class EvalScenario:
    """评估场景定义

    定义一个完整的对话场景和预期结果。

    Attributes:
        name: 场景名称
        description: 场景描述
        messages: 对话消息列表
        expected_actions: 预期 Agent 行为列表（顺序敏感）
        expected_content_keywords: 预期写入内容的关键词（用于验证内容质量）
        current_preferences: 当前 preferences.md 内容（模拟已有记忆）
        current_behaviors: 当前 behaviors.md 内容（模拟已有记忆）
    """

    name: str
    description: str
    messages: list[tuple[str, str]]  # (role, content)
    expected_actions: list[ExpectedAction]
    expected_content_keywords: list[str] = field(default_factory=list)
    current_preferences: str = ""
    current_behaviors: str = ""


# ============================================================================
# 评估场景库
# ============================================================================


# 场景 1：明确的偏好反馈
SCENARIO_1_PREF_FEEDBACK = EvalScenario(
    name="preference_feedback",
    description="用户表达明确的偏好反馈，应写入 preferences",
    messages=[
        ("human", "回答简洁一点，不要写那么多废话，直接给方案就行"),
        ("ai", "明白了，我会更简洁地回答。根据你的问题，方案是..."),
    ],
    expected_actions=[
        ExpectedAction.WRITE_PREFERENCES,
        ExpectedAction.UPDATE_MEMORY_INDEX,
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
    expected_content_keywords=["简洁", "不喜欢", "废话"],
)

# 场景 2：负向反馈处理
SCENARIO_2_NEGATIVE_FEEDBACK = EvalScenario(
    name="negative_feedback",
    description="用户给出负向反馈，应正确处理",
    messages=[
        ("human", "你之前说 Rust 比 Go 快，这个说法不准确，不要这么绝对"),
        ("ai", "感谢纠正，我会更谨慎地表述性能对比..."),
    ],
    expected_actions=[
        ExpectedAction.WRITE_PREFERENCES,
        ExpectedAction.UPDATE_MEMORY_INDEX,
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
    expected_content_keywords=["不喜欢", "绝对", "谨慎"],
)

# 场景 3：观察到行为模式（单次）
SCENARIO_3_BEHAVIOR_SINGLE = EvalScenario(
    name="behavior_single_instance",
    description="只观察到一次行为模式，不应写入（需要至少2次确认）",
    messages=[
        ("human", "RAG 的原理是什么？"),
        ("ai", "RAG (Retrieval-Augmented Generation) 的原理是..."),
        ("human", "具体怎么实现？"),
        ("ai", "实现步骤如下..."),
    ],
    expected_actions=[
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
)

# 场景 4：观察到行为模式（多次重复）
SCENARIO_4_BEHAVIOR_REPEATED = EvalScenario(
    name="behavior_repeated_pattern",
    description="观察到重复的行为模式，应写入 behaviors",
    messages=[
        ("human", "RAG 的原理是什么？"),
        ("ai", "RAG 的原理是..."),
        ("human", "具体怎么实现？"),
        ("ai", "实现步骤如下..."),
        ("human", "Embedding 的原理是什么？"),
        ("ai", "Embedding 的原理是..."),
        ("human", "代码怎么写？"),
        ("ai", "代码示例..."),
        ("human", "Vector DB 的原理是什么？"),
        ("ai", "Vector DB 的原理是..."),
        ("human", "Qdrant 怎么配置？"),
        ("ai", "Qdrant 配置方法..."),
    ],
    expected_actions=[
        ExpectedAction.WRITE_BEHAVIORS,
        ExpectedAction.UPDATE_MEMORY_INDEX,
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
    expected_content_keywords=["先问原理", "追问实现", "提问模式"],
)

# 场景 5：有检索价值的对话
SCENARIO_5_SESSION_SUMMARY = EvalScenario(
    name="session_summary_valuable",
    description="解决了具体技术问题，应写入 session_summary",
    messages=[
        ("human", "Qdrant 的 Payload 过滤怎么优化召回率？"),
        ("ai", "可以使用复合条件过滤，先按 payload 硬过滤再向量计算..."),
        ("human", "这个方案可行，我试试"),
        ("ai", "好的，如果遇到问题可以继续讨论"),
    ],
    expected_actions=[
        ExpectedAction.WRITE_SESSION_SUMMARY,
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
    expected_content_keywords=["Qdrant", "Payload", "召回"],
)

# 场景 6：不值得记忆的闲聊
SCENARIO_6_CHAT_NO_VALUE = EvalScenario(
    name="chat_no_memory_value",
    description="闲聊内容，不值得记忆",
    messages=[
        ("human", "今天天气怎么样？"),
        ("ai", "抱歉，我没有天气查询能力"),
        ("human", "好吧，没关系"),
        ("ai", "有什么其他问题我可以帮你解答"),
    ],
    expected_actions=[
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
)

# 场景 7：模糊表达不写入
SCENARIO_7_VAGUE_EXPRESSION = EvalScenario(
    name="vague_expression",
    description="模糊表达，无明确意图",
    messages=[
        ("human", "嗯...还行吧"),
        ("ai", "有什么可以改进的地方吗？"),
        ("human", "没什么特别的要求"),
        ("ai", "好的，继续聊"),
    ],
    expected_actions=[
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
)

# 场景 8：偏好冲突处理
SCENARIO_8_PREF_CONFLICT = EvalScenario(
    name="preference_conflict",
    description="新偏好与旧偏好冲突，应替换",
    messages=[
        ("human", "之前说简洁回答，但我现在发现有时候还是需要详细解释的"),
        ("ai", "明白了，我会根据问题复杂度调整解释深度"),
    ],
    current_preferences="""
# 用户偏好详情

## 响应风格
- 偏好：简洁直接，先给方案再解释
- 不喜欢：冗长解释、过多的背景铺垫
""",
    expected_actions=[
        ExpectedAction.WRITE_PREFERENCES,
        ExpectedAction.UPDATE_MEMORY_INDEX,
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
    expected_content_keywords=["根据复杂度", "调整"],
)

# 场景 9：偏好重复不写入
SCENARIO_9_PREF_DUPLICATE = EvalScenario(
    name="preference_duplicate",
    description="新偏好与旧偏好一致，不应重复写入",
    messages=[
        ("human", "回答简洁一点就行"),
        ("ai", "好的，我会简洁回答"),
    ],
    current_preferences="""
# 用户偏好详情

## 响应风格
- 偏好：简洁直接
- 不喜欢：冗长解释
""",
    expected_actions=[
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
)

# 场景 10：session_summary 去重
SCENARIO_10_SUMMARY_DUPLICATE = EvalScenario(
    name="session_summary_duplicate_topic",
    description="与已有摘要主题相似，不应重复写入",
    messages=[
        ("human", "上次说的 Qdrant Payload 过滤，我再问一下具体参数怎么设？"),
        ("ai", "参数建议设置 filter 条件..."),
    ],
    expected_actions=[
        ExpectedAction.ONLY_UPDATE_CURSOR,
    ],
)

# 所有场景集合
ALL_SCENARIOS = [
    SCENARIO_1_PREF_FEEDBACK,
    SCENARIO_2_NEGATIVE_FEEDBACK,
    SCENARIO_3_BEHAVIOR_SINGLE,
    SCENARIO_4_BEHAVIOR_REPEATED,
    SCENARIO_5_SESSION_SUMMARY,
    SCENARIO_6_CHAT_NO_VALUE,
    SCENARIO_7_VAGUE_EXPRESSION,
    SCENARIO_8_PREF_CONFLICT,
    SCENARIO_9_PREF_DUPLICATE,
    SCENARIO_10_SUMMARY_DUPLICATE,
]


# ============================================================================
# 评估工具函数
# ============================================================================


def build_messages_from_scenario(scenario: EvalScenario) -> list:
    """从场景构建 LangChain 消息列表"""
    messages = []
    for role, content in scenario.messages:
        msg_id = str(uuid.uuid4())
        if role == "human":
            messages.append(HumanMessage(content=content, id=msg_id))
        else:
            messages.append(AIMessage(content=content, id=msg_id))
    return messages


def capture_tool_calls(invocation_result: dict) -> list[tuple[str, dict]]:
    """从 Agent 执行结果中提取工具调用

    Args:
        invocation_result: Agent.ainvoke() 返回的结果

    Returns:
        工具调用列表：[(tool_name, tool_args), ...]
    """
    tool_calls = []

    # LangChain Agent 的结果结构通常是 {"messages": [...]}
    if "messages" not in invocation_result:
        return tool_calls

    for msg in invocation_result["messages"]:
        # AIMessage 可能包含 tool_calls 属性
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append((tc.get("name", ""), tc.get("args", {})))

    return tool_calls


def check_action_sequence(
    tool_calls: list[tuple[str, dict]],
    expected_actions: list[ExpectedAction],
) -> tuple[bool, str]:
    """检查工具调用序列是否符合预期

    Args:
        tool_calls: 实际工具调用列表
        expected_actions: 预期行为列表

    Returns:
        (是否匹配, 错误描述)

    逻辑说明：
        - ONLY_UPDATE_CURSOR 在预期列表末尾表示"cursor 必须最后调用"
        - 如果预期列表只有 ONLY_UPDATE_CURSOR，表示"只调用 cursor，不调用其他工具"
        - 其他 ExpectedAction 表示应该调用对应的工具
    """
    # 工具名称映射
    action_to_tool = {
        ExpectedAction.WRITE_PREFERENCES: "update_preferences",
        ExpectedAction.WRITE_BEHAVIORS: "update_behaviors",
        ExpectedAction.WRITE_SESSION_SUMMARY: "write_session_summary",
        ExpectedAction.UPDATE_MEMORY_INDEX: "update_memory_index",
        ExpectedAction.ONLY_UPDATE_CURSOR: "update_cursor",
    }

    # 提取实际调用的工具名称（按顺序）
    actual_tools = [tc[0] for tc in tool_calls]

    # 检查 update_cursor 是否在最后
    if "update_cursor" not in actual_tools:
        return False, "必须调用 update_cursor，但未找到"

    cursor_index = actual_tools.index("update_cursor")
    if cursor_index != len(actual_tools) - 1:
        return False, f"update_cursor 应该是最后调用，实际位置: {cursor_index + 1}/{len(actual_tools)}"

    # 检查 update_memory_index 是否跟随 preferences/behaviors
    if "update_memory_index" in actual_tools:
        idx = actual_tools.index("update_memory_index")
        # 检查之前是否有 update_preferences 或 update_behaviors
        before = actual_tools[:idx]
        if "update_preferences" not in before and "update_behaviors" not in before:
            return False, "update_memory_index 应该在 update_preferences 或 update_behaviors 之后调用"

    # 判断是否是"只调用 cursor"的场景
    only_cursor_expected = (
        len(expected_actions) == 1 and
        expected_actions[0] == ExpectedAction.ONLY_UPDATE_CURSOR
    )

    if only_cursor_expected:
        # 只应调用 update_cursor
        if len(actual_tools) != 1:
            extra_tools = set(actual_tools) - {"update_cursor"}
            return False, f"不应调用额外工具: {extra_tools}"
    else:
        # 检查所有预期工具都被调用（排除 ONLY_UPDATE_CURSOR，因为它只表示"最后调用"）
        expected_tools_except_cursor = [
            action_to_tool[action]
            for action in expected_actions
            if action != ExpectedAction.ONLY_UPDATE_CURSOR
        ]

        for expected_tool in expected_tools_except_cursor:
            if expected_tool not in actual_tools:
                return False, f"预期调用 {expected_tool}，但未找到"

    return True, ""


def check_content_keywords(
    tool_calls: list[tuple[str, dict]],
    expected_keywords: list[str],
) -> tuple[bool, str]:
    """检查写入内容是否包含预期关键词

    Args:
        tool_calls: 工具调用列表
        expected_keywords: 预期关键词列表

    Returns:
        (是否包含, 缺失关键词)
    """
    if not expected_keywords:
        return True, ""

    # 找到 preferences 或 behaviors 的内容参数
    for tool_name, args in tool_calls:
        if tool_name in ["update_preferences", "update_behaviors"]:
            content = args.get("content", "")
            missing = []
            for kw in expected_keywords:
                if kw not in content:
                    missing.append(kw)
            if missing:
                return False, f"内容缺失关键词: {missing}"
            return True, ""

    return True, ""


# ============================================================================
# 评估测试类
# ============================================================================


@pytest.mark.eval
class TestMemoryAgentEvaluation:
    """Memory Agent 评估测试

    使用真实 LLM 执行 Agent，验证其决策准确性。
    """

    @pytest.fixture
    def mock_repositories(self):
        """Mock 仓库，避免写入真实数据库"""
        mock_memory_repo = MagicMock()
        mock_memory_repo.read_reference.return_value = ""
        mock_memory_repo.write_reference.return_value = None
        mock_memory_repo.write_content.return_value = None

        mock_summary_repo = MagicMock()
        mock_summary_repo.create.return_value = None
        mock_summary_repo.get_recent.return_value = []

        return {
            "memory_repo": mock_memory_repo,
            "summary_repo": mock_summary_repo,
        }

    @pytest.fixture
    def mock_embedding(self):
        """Mock Embedding"""
        mock = MagicMock()
        mock.embed.return_value = [0.1] * 1024
        return mock

    def _run_scenario_with_real_llm(
        self,
        scenario: EvalScenario,
        mock_repositories: dict,
        mock_embedding,
    ) -> dict:
        """使用真实 LLM 运行场景

        Args:
            scenario: 评估场景
            mock_repositories: Mock 仓库
            mock_embedding: Mock Embedding

        Returns:
            Agent 执行结果
        """
        from app.application.agents.memory.agent import create_memory_agent, PROMPTS_DIR
        from app.infrastructure.common.prompt import build_prompt

        # 构建 context
        messages = build_messages_from_scenario(scenario)
        latest_uuid = messages[-1].id if messages else ""

        formatted_messages = "\n".join([
            f"{'用户' if isinstance(m, HumanMessage) else 'AI'}: {m.content[:200]}..."
            for m in messages
        ])

        context = {
            "new_messages": formatted_messages,
            "current_preferences": scenario.current_preferences,
            "current_behaviors": scenario.current_behaviors,
            "conversation_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "cursor_uuid": latest_uuid,
        }

        # Mock 仓库和 embedding - 修改路径为正确的导入位置
        with patch("app.infrastructure.persistence.postgres.get_memory_repository") as mock_get_memory:
            with patch("app.infrastructure.persistence.postgres.get_session_summary_repository") as mock_get_summary:
                with patch("app.infrastructure.adapters.embedding_adapter.get_embedding_adapter") as mock_get_emb:
                    # 配置 mock 返回值
                    mock_memory_repo = mock_repositories["memory_repo"]
                    mock_summary_repo = mock_repositories["summary_repo"]

                    # get_memory_repository 返回上下文管理器
                    mock_get_memory.return_value.__enter__ = lambda self: mock_memory_repo
                    mock_get_memory.return_value.__exit__ = lambda self, *args: None

                    mock_get_summary.return_value = mock_summary_repo
                    mock_get_emb.return_value = mock_embedding

                    # Mock cursor 模块
                    with patch("app.application.agents.memory.cursor.save_cursor") as mock_save_cursor:
                        mock_save_cursor.return_value = None

                        # 创建并执行 Agent
                        agent = create_memory_agent()

                        input_messages = [HumanMessage(content=build_prompt(
                            "memory_agent.md",
                            PROMPTS_DIR,
                            new_messages=context["new_messages"],
                            current_preferences=context["current_preferences"],
                            current_behaviors=context["current_behaviors"],
                            conversation_id=context["conversation_id"],
                            user_id=context["user_id"],
                            cursor_uuid=context["cursor_uuid"],
                        ))]

                        result = agent.invoke({"messages": input_messages})

        return result

    # ========================================================================
    # 单场景测试
    # ========================================================================

    @pytest.mark.eval
    @pytest.mark.asyncio
    async def test_scenario_1_preference_feedback(self, mock_repositories, mock_embedding):
        """评估：明确的偏好反馈"""
        scenario = SCENARIO_1_PREF_FEEDBACK

        result = self._run_scenario_with_real_llm(scenario, mock_repositories, mock_embedding)
        tool_calls = capture_tool_calls(result)

        # 检查工具调用序列
        matched, error = check_action_sequence(tool_calls, scenario.expected_actions)
        assert matched, f"场景 {scenario.name}: {error}"

        # 检查内容关键词
        content_ok, content_error = check_content_keywords(tool_calls, scenario.expected_content_keywords)
        assert content_ok, f"场景 {scenario.name}: {content_error}"

    @pytest.mark.eval
    @pytest.mark.asyncio
    async def test_scenario_6_chat_no_value(self, mock_repositories, mock_embedding):
        """评估：闲聊不值得记忆"""
        scenario = SCENARIO_6_CHAT_NO_VALUE

        result = self._run_scenario_with_real_llm(scenario, mock_repositories, mock_embedding)
        tool_calls = capture_tool_calls(result)

        # 应只调用 update_cursor
        matched, error = check_action_sequence(tool_calls, scenario.expected_actions)
        assert matched, f"场景 {scenario.name}: {error}"

    @pytest.mark.eval
    @pytest.mark.asyncio
    async def test_scenario_3_behavior_single_instance(self, mock_repositories, mock_embedding):
        """评估：单次行为模式不应写入"""
        scenario = SCENARIO_3_BEHAVIOR_SINGLE

        result = self._run_scenario_with_real_llm(scenario, mock_repositories, mock_embedding)
        tool_calls = capture_tool_calls(result)

        # 应只调用 update_cursor
        matched, error = check_action_sequence(tool_calls, scenario.expected_actions)
        assert matched, f"场景 {scenario.name}: {error}"

    # ========================================================================
    # 批量评估测试
    # ========================================================================

    @pytest.mark.eval
    @pytest.mark.slow
    async def test_all_scenarios_batch(self, mock_repositories, mock_embedding):
        """批量评估所有场景

        输出详细报告，展示每个场景的评估结果。
        """
        results = []

        for scenario in ALL_SCENARIOS:
            try:
                result = self._run_scenario_with_real_llm(scenario, mock_repositories, mock_embedding)
                tool_calls = capture_tool_calls(result)

                matched, error = check_action_sequence(tool_calls, scenario.expected_actions)
                content_ok, content_error = check_content_keywords(tool_calls, scenario.expected_content_keywords)

                results.append({
                    "scenario": scenario.name,
                    "passed": matched and content_ok,
                    "action_error": error,
                    "content_error": content_error,
                    "tool_calls": [tc[0] for tc in tool_calls],
                })
            except Exception as e:
                results.append({
                    "scenario": scenario.name,
                    "passed": False,
                    "action_error": str(e),
                    "content_error": "",
                    "tool_calls": [],
                })

        # 输出报告
        passed_count = sum(1 for r in results if r["passed"])
        total_count = len(results)

        report_lines = [
            "\n" + "=" * 60,
            "Memory Agent 评估报告",
            "=" * 60,
            f"总计: {passed_count}/{total_count} 通过",
            "-" * 60,
        ]

        for r in results:
            status = "✓" if r["passed"] else "✗"
            report_lines.append(f"{status} {r['scenario']}")
            if not r["passed"]:
                if r["action_error"]:
                    report_lines.append(f"  行为错误: {r['action_error']}")
                if r["content_error"]:
                    report_lines.append(f"  内容错误: {r['content_error']}")
                report_lines.append(f"  实际调用: {r['tool_calls']}")

        report_lines.append("=" * 60)

        print("\n".join(report_lines))

        # 断言至少 80% 通过
        pass_rate = passed_count / total_count
        assert pass_rate >= 0.8, f"通过率 {pass_rate:.1%} < 80%"


# ============================================================================
# 手动测试工具
# ============================================================================


def run_manual_evaluation():
    """手动运行评估，用于调试

    使用方法：
        cd backend
        PYTHONPATH=. uv run python -m tests.memory.test_memory_eval
    """
    import asyncio

    async def main():
        test_instance = TestMemoryAgentEvaluation()

        # 创建 mock
        mock_repositories = {
            "memory_repo": MagicMock(),
            "summary_repo": MagicMock(),
        }
        mock_repositories["memory_repo"].read_reference.return_value = ""
        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [0.1] * 1024

        # 运行批量测试
        await test_instance.test_all_scenarios_batch(mock_repositories, mock_embedding)

    asyncio.run(main())


if __name__ == "__main__":
    run_manual_evaluation()


__all__ = [
    "EvalScenario",
    "ExpectedAction",
    "ALL_SCENARIOS",
    "TestMemoryAgentEvaluation",
    "run_manual_evaluation",
]