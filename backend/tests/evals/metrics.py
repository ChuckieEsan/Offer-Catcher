"""Agent 评估指标

实现核心评估指标：
1. task_completion_score - 任务完成率
2. tool_correctness_score - 工具调用正确性
3. extract_tools_from_result - 从结果提取工具序列
"""

from typing import Any


def extract_tools_from_result(result: dict) -> list[str]:
    """从 Agent 执行结果中提取工具调用序列

    Args:
        result: Agent 执行结果（包含 messages 字段）

    Returns:
        工具名称列表（按调用顺序）
    """
    tools = []
    messages = result.get("messages", [])

    for msg in messages:
        # 检查 AIMessage 的 tool_calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if tool_name:
                    tools.append(tool_name)

    return tools


def tool_correctness_score(
    actual_tools: list[str],
    expected_tools: list[str],
) -> dict:
    """评估工具调用正确性

    Args:
        actual_tools: 实际调用的工具列表
        expected_tools: 预期调用的工具列表

    Returns:
        {"score": 0-1, "reason": "...", "correct": bool}
    """
    if not expected_tools:
        return {"score": 1.0, "reason": "No expected tools", "correct": True}

    actual_set = set(actual_tools)
    expected_set = set(expected_tools)

    # 计算召回率（预期工具是否被调用）
    recalled = len(expected_set & actual_set)
    recall = recalled / len(expected_set)

    # 计算精确率（调用的工具是否都是预期的）
    if actual_set:
        precision = len(expected_set & actual_set) / len(actual_set)
    else:
        precision = 0.0

    # 综合评分：F1 score
    if recall + precision > 0:
        f1 = 2 * recall * precision / (recall + precision)
    else:
        f1 = 0.0

    # 判断是否正确
    correct = recall >= 0.8 and len(actual_set - expected_set) <= 2

    reason_parts = []
    if recall < 1.0:
        missing = expected_set - actual_set
        reason_parts.append(f"缺少工具: {missing}")
    if precision < 1.0:
        extra = actual_set - expected_set
        reason_parts.append(f"额外工具: {extra}")

    return {
        "score": f1,
        "reason": "; ".join(reason_parts) if reason_parts else "工具调用正确",
        "correct": correct,
        "recall": recall,
        "precision": precision,
    }


def task_completion_score(
    agent_output: str,
    user_intent: str,
    expected_keywords: list[str] | None = None,
    ground_truth: str | None = None,
) -> dict:
    """评估任务完成率

    Args:
        agent_output: Agent 的最终输出
        user_intent: 用户意图（原始输入）
        expected_keywords: 预期包含的关键词
        ground_truth: 标准答案（可选）

    Returns:
        {"score": 0-1, "reason": "...", "completed": bool}
    """
    if not agent_output:
        return {"score": 0.0, "reason": "无输出", "completed": False}

    # 1. 检查关键词覆盖率
    keyword_score = 0.0
    if expected_keywords:
        matched = sum(1 for kw in expected_keywords if kw.lower() in agent_output.lower())
        keyword_score = matched / len(expected_keywords)

    # 2. 检查输出长度（过短可能未完成）
    length_score = min(1.0, len(agent_output) / 100)

    # 3. 综合评分
    if ground_truth:
        # 如果有标准答案，检查相似度（简单匹配）
        ground_truth_lower = ground_truth.lower()
        output_lower = agent_output.lower()
        similarity = sum(1 for word in ground_truth_lower.split() if word in output_lower) / max(1, len(ground_truth_lower.split()))
        final_score = (keyword_score * 0.4 + length_score * 0.2 + similarity * 0.4)
    else:
        final_score = (keyword_score * 0.6 + length_score * 0.4)

    # 判断是否完成
    completed = final_score >= 0.7

    reason_parts = []
    if expected_keywords and keyword_score < 1.0:
        missing_kw = [kw for kw in expected_keywords if kw.lower() not in agent_output.lower()]
        reason_parts.append(f"缺少关键词: {missing_kw}")
    if length_score < 0.5:
        reason_parts.append("输出过短")

    return {
        "score": final_score,
        "reason": "; ".join(reason_parts) if reason_parts else "任务完成",
        "completed": completed,
        "keyword_score": keyword_score,
        "length_score": length_score,
    }


def detect_repeated_calls(tool_calls: list[str], threshold: int = 2) -> list[str]:
    """检测重复的工具调用（可能死循环）

    Args:
        tool_calls: 工具调用序列
        threshold: 重复次数阈值

    Returns:
        重复调用的工具名称列表
    """
    from collections import Counter
    counts = Counter(tool_calls)
    return [tool for tool, count in counts.items() if count > threshold]


def evaluate_agent_trajectory(
    result: dict,
    test_case: dict,
) -> dict:
    """综合评估 Agent 轨迹

    Args:
        result: Agent 执行结果
        test_case: 测试用例定义

    Returns:
        综合评估结果
    """
    # 提取工具调用
    actual_tools = extract_tools_from_result(result)
    expected_tools = test_case.get("expected_tools", [])

    # 工具正确性评估
    tool_eval = tool_correctness_score(actual_tools, expected_tools)

    # 任务完成率评估
    output = result.get("response_to_user", "")
    keywords = test_case.get("expected_keywords")
    ground_truth = test_case.get("ground_truth")
    task_eval = task_completion_score(output, test_case["input"], keywords, ground_truth)

    # 死循环检测
    repeated_tools = detect_repeated_calls(actual_tools)
    has_loop = len(repeated_tools) > 0 and test_case.get("should_not_loop", False)

    # 综合评分
    overall_score = (tool_eval["score"] * 0.4 + task_eval["score"] * 0.6)
    if has_loop:
        overall_score *= 0.5  # 死循环扣分

    return {
        "overall_score": overall_score,
        "tool_eval": tool_eval,
        "task_eval": task_eval,
        "actual_tools": actual_tools,
        "repeated_tools": repeated_tools,
        "has_loop": has_loop,
        "passed": overall_score >= 0.7 and not has_loop,
    }


__all__ = [
    "extract_tools_from_result",
    "tool_correctness_score",
    "task_completion_score",
    "detect_repeated_calls",
    "evaluate_agent_trajectory",
]