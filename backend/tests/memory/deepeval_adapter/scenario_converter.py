"""EvalScenario 转换为 DeepEval LLMTestCase

将现有的测试场景转换为 DeepEval 框架所需的格式。
"""

import json
from typing import Any

from deepeval.test_case import LLMTestCase


def scenario_to_test_case(
    scenario_name: str,
    messages: list[tuple[str, str]],
    agent_result: dict,
    expected_actions: list,
    current_preferences: str = "",
    current_behaviors: str = "",
    expected_keywords: list[str] = [],
) -> LLMTestCase:
    """将 EvalScenario 转换为 DeepEval LLMTestCase

    Args:
        scenario_name: 场景名称
        messages: 对话消息列表 [(role, content), ...]
        agent_result: Agent 执行结果
        expected_actions: 预期行为列表（ExpectedAction）
        current_preferences: 当前偏好内容
        current_behaviors: 当前行为模式内容
        expected_keywords: 期望关键词列表

    Returns:
        LLMTestCase 实例
    """
    # 格式化对话作为 input
    conversation = format_conversation(messages)

    # Agent 决策作为 actual_output
    actual_decision = format_agent_decision(agent_result)

    # 预期决策作为 expected_output
    expected_decision = format_expected_decision(expected_actions)

    # 已有记忆作为 context
    context = format_context(current_preferences, current_behaviors)

    return LLMTestCase(
        input=conversation,
        actual_output=actual_decision,
        expected_output=expected_decision,
        context=context,
        additional_metadata={
            "scenario_name": scenario_name,
            "expected_keywords": expected_keywords,
        },
    )


def format_conversation(messages: list[tuple[str, str]]) -> str:
    """格式化对话内容

    Args:
        messages: [(role, content), ...] 格式的消息列表

    Returns:
        格式化的对话文本
    """
    lines = []
    for role, content in messages:
        speaker = "用户" if role == "human" else "AI"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def format_agent_decision(agent_result: dict) -> str:
    """格式化 Agent 决策

    Args:
        agent_result: Agent 执行结果，包含 tool_calls 等

    Returns:
        格式化的决策文本
    """
    tool_calls = agent_result.get("tool_calls", [])
    tool_calls_detail = agent_result.get("tool_calls_detail", [])
    decision_reason = agent_result.get("decision_reason", "")

    # 构建决策描述
    decision_parts = []

    if decision_reason:
        decision_parts.append(f"决策原因: {decision_reason}")

    if tool_calls:
        decision_parts.append(f"工具调用列表: {json.dumps(tool_calls)}")

    if tool_calls_detail:
        for name, args in tool_calls_detail:
            if name in ["update_preferences", "update_behaviors"]:
                content_preview = args.get("content", "")[:100]
                decision_parts.append(f"{name}: {content_preview}...")
            elif name == "write_session_summary":
                summary_preview = args.get("summary", "")[:100]
                decision_parts.append(f"{name}: {summary_preview}...")
            else:
                decision_parts.append(f"{name}: 已调用")

    return "\n".join(decision_parts) if decision_parts else "仅更新游标，无记忆写入"


def format_expected_decision(expected_actions: list) -> str:
    """格式化预期决策

    Args:
        expected_actions: ExpectedAction 枚举列表

    Returns:
        格式化的预期决策文本
    """
    # 导入 ExpectedAction（延迟导入避免循环依赖）
    from tests.memory.test_memory_eval import ExpectedAction

    expected_parts = []

    # 判断是否只更新游标
    only_cursor = (
        len(expected_actions) == 1
        and expected_actions[0] == ExpectedAction.ONLY_UPDATE_CURSOR
    )

    if only_cursor:
        return "预期：仅更新游标，不写入任何记忆"

    # 其他情况
    for action in expected_actions:
        if action == ExpectedAction.WRITE_PREFERENCES:
            expected_parts.append("预期写入 preferences")
        elif action == ExpectedAction.WRITE_BEHAVIORS:
            expected_parts.append("预期写入 behaviors")
        elif action == ExpectedAction.WRITE_SESSION_SUMMARY:
            expected_parts.append("预期写入 session_summary")
        elif action == ExpectedAction.UPDATE_MEMORY_INDEX:
            expected_parts.append("预期更新 memory_index")
        elif action == ExpectedAction.ONLY_UPDATE_CURSOR:
            expected_parts.append("预期更新游标")

    return "\n".join(expected_parts)


def format_context(
    current_preferences: str,
    current_behaviors: str,
) -> list[str]:
    """格式化已有记忆上下文

    Args:
        current_preferences: 当前偏好内容
        current_behaviors: 当前行为模式内容

    Returns:
        DeepEval 所需的 context 字符串列表
    """
    parts = []

    if current_preferences:
        parts.append(f"已有偏好:\n{current_preferences[:500]}")

    if current_behaviors:
        parts.append(f"已有行为模式:\n{current_behaviors[:500]}")

    return parts if parts else ["（无已有记忆）"]


__all__ = [
    "scenario_to_test_case",
    "format_conversation",
    "format_agent_decision",
    "format_expected_decision",
]