"""LLM-as-Judge 评估 Prompt 模板

定义各类评估场景的 Prompt 模板，
用于 Extraction、Utilization、Multi-turn 评测。
"""

from typing import Any


# ============================================================================
# Extraction Decision 评估 Prompt
# ============================================================================

EXTRACTION_DECISION_PROMPT = """你是一个记忆系统评测专家。请评估 Memory Agent 的决策是否正确。

## 评估维度

### 1. 应该记忆判断 (should_remember)
评估用户是否表达了值得长期记忆的信息：

**应该写入长期记忆**：
- 用户明确说"以后都..."、"我喜欢..."、"我不喜欢..."
- 用户给出反馈"这个太.../不够..."
- 用户表达期望"希望你能..."
- 用户纠正你的行为"不要这样..."
- 深度讨论某个话题（>=3轮追问）
- 观察到重复的行为模式（>=2次相同序列）

**不应写入长期记忆**：
- 临时约束："这次"、"这道题"、"先"、"现在"
- 闲聊、确认、感谢
- 隐私信息、密码、个人信息
- 简单问答（<=2轮）
- 情绪表达（"今天累了"）

### 2. 记忆类型判断 (memory_type_correct)
判断记忆类型是否正确：

- **preferences**: 用户主动表达的偏好、反馈、要求
- **behaviors**: 观察到的重复行为模式（需要至少2次确认）
- **session_summary**: 深度讨论或有结论的对话（>=3轮）

### 3. 临时约束识别 (temporary_constraint_detected)
检查是否正确识别临时约束：
- 包含"这次"、"这道题"、"先"、"后面再"等临时性表达
- 临时约束不应写入长期记忆

### 4. 去重判断 (dedup_correct)
检查去重是否正确：
- 新内容与已有内容语义相似 → 应跳过
- 语义等价："简洁" ≈ "简洁直接" ≈ "不要太长"

## 输入信息

### 对话内容
{conversation}

### 已有记忆
Preferences:
{existing_preferences}

Behaviors:
{existing_behaviors}

Session Summaries:
{existing_summaries}

### Agent 实际决策
工具调用列表: {tool_calls}
是否写入 preferences: {wrote_preferences}
是否写入 behaviors: {wrote_behaviors}
是否写入 session_summary: {wrote_session_summary}
只更新 cursor: {only_cursor}

## 输出格式

请输出 JSON：
```json
{
  "should_remember_score": 1-5,
  "should_remember_reason": "解释",
  "memory_type_correct": true/false,
  "memory_type_expected": "preferences|behaviors|session_summary|none",
  "memory_type_actual": "preferences|behaviors|session_summary|none",
  "temporary_constraint_detected": true/false,
  "temporary_constraint_in_input": true/false,
  "dedup_correct": true/false,
  "dedup_needed": true/false,
  "overall_score": 1-5,
  "passed": true/false,
  "reason": "简短总结"
}
```
"""


# ============================================================================
# Content Quality 评估 Prompt
# ============================================================================

CONTENT_QUALITY_PROMPT = """你是一个记忆内容质量评估专家。请评估提取的记忆内容质量。

## 评估维度

### 1. 完整性 (completeness)
- 是否捕获了关键信息？
- 是否遗漏重要细节？
- 关键词是否完整？

### 2. 准确性 (accuracy)
- 内容是否准确反映用户意图？
- 是否有误解或歪曲？
- 是否与对话内容一致？

### 3. 结构化 (structured)
- 是否符合记忆格式规范？
- 偏好是否包含 Why/How to apply？
- 行为模式是否包含 Evidence？
- 摘要是否包含 topics/importance？

### 4. 去噪性 (noise_free)
- 是否过滤了无关信息？
- 是否包含冗余内容？
- 是否有情绪词/噪音词？

## 输入信息

### 原始对话
{conversation}

### 提取的记忆内容
{extracted_content}

### 记忆类型
{memory_type}

### 期望关键词
{expected_keywords}

## 输出格式

请输出 JSON：
```json
{
  "completeness": 1-5,
  "completeness_reason": "解释",
  "accuracy": 1-5,
  "accuracy_reason": "解释",
  "structured": 1-5,
  "structured_reason": "解释",
  "noise_free": 1-5,
  "noise_free_reason": "解释",
  "overall_score": 1-5,
  "missing_keywords": ["关键词1", "关键词2"],
  "extra_noise": ["噪音内容"],
  "passed": true/false,
  "reason": "简短总结"
}
```
"""


# ============================================================================
# Utilization Pairwise 评估 Prompt
# ============================================================================

UTILIZATION_PAIRWISE_PROMPT = """你是一个回答质量评估专家。请对比两个回答的质量。

## 背景

用户有一个偏好/历史记忆。我们评估两个回答：
- 回答 A：使用记忆系统的回答
- 回答 B：不使用记忆系统的回答

## 评估维度

### 1. 任务正确性 (task_correctness)
回答是否正确解决了用户问题？
- 完全正确：5分
- 大部分正确：4分
- 基本正确但有错误：3分
- 有明显错误：2分
- 完全错误：1分

### 2. 个性化匹配 (personalization_fit)
回答是否体现了对用户偏好的理解？
- 完全符合偏好：5分
- 大部分符合：4分
- 基本符合但有偏离：3分
- 有明显偏离：2分
- 完全不符合：1分

### 3. 历史一致性 (historical_consistency)
是否正确引用了历史讨论？是否与之前对话一致？

### 4. 记忆利用 (memory_utilization)
记忆是否被有效利用？
- 有效利用（真正改善了回答）：5分
- 提及但未改善：3分
- 未使用：1分

### 5. 噪音排除 (noise_exclusion)
是否避免了引用无关记忆？

## 输入信息

### 用户问题
{query}

### 用户记忆
{memory}

### 回答 A（有记忆）
{answer_a}

### 回答 B（无记忆）
{answer_b}

## 输出格式

请输出 JSON：
```json
{
  "winner": "A" | "B" | "tie",
  "task_correctness": { "a": 1-5, "b": 1-5 },
  "personalization_fit": { "a": 1-5, "b": 1-5 },
  "historical_consistency": { "a": 1-5, "b": 1-5 },
  "memory_utilization": { "a": 1-5 },
  "noise_exclusion": { "a": 1-5, "b": 1-5 },
  "memory_helpful": true/false,
  "delta_score": 数字（A总分 - B总分）,
  "reason": "简短解释为什么 A/B 更好"
}
```
"""


# ============================================================================
# Multi-turn Consistency 评估 Prompt
# ============================================================================

MULTI_TURN_CONSISTENCY_PROMPT = """你是一个对话一致性评估专家。请评估多轮对话中记忆的使用一致性。

## 评估维度

### 1. 记忆状态一致性 (memory_state_consistent)
- 新记忆是否与已有记忆冲突？
- 冲突时是否正确更新而非矛盾？

### 2. 引用一致性 (reference_consistent)
- 对同一历史事件的引用是否一致？
- 是否有前后矛盾？

### 3. 偏好演进 (preference_evolution)
- 偏好变化是否有清晰轨迹？
- 是否正确处理偏好更新？

### 4. 遗忘检测 (forgetting_detected)
- 是否正确遗忘过时信息？
- 是否错误遗忘重要信息？

## 输入信息

### 对话历史
{conversation_history}

### 记忆演进轨迹
{memory_evolution}

### 当前回答
{current_response}

## 输出格式

请输出 JSON：
```json
{
  "memory_state_consistent": true/false,
  "memory_state_conflicts": ["冲突描述"],
  "reference_consistent": true/false,
  "reference_conflicts": ["引用冲突"],
  "preference_evolution": "correct|incorrect|none",
  "preference_evolution_detail": "描述",
  "forgetting_detected": true/false,
  "forgetting_type": "correct|incorrect|none",
  "consistency_score": 1-5,
  "passed": true/false,
  "reason": "简短解释"
}
```
"""


# ============================================================================
# Judge Prompt 渲染函数
# ============================================================================


def render_extraction_prompt(
    conversation: str,
    existing_preferences: str = "",
    existing_behaviors: str = "",
    existing_summaries: str = "",
    tool_calls: list[str] = [],
    wrote_preferences: bool = False,
    wrote_behaviors: bool = False,
    wrote_session_summary: bool = False,
    only_cursor: bool = False,
) -> str:
    """渲染 Extraction 评估 Prompt"""
    return EXTRACTION_DECISION_PROMPT.format(
        conversation=conversation,
        existing_preferences=existing_preferences or "（无）",
        existing_behaviors=existing_behaviors or "（无）",
        existing_summaries=existing_summaries or "（无）",
        tool_calls=json.dumps(tool_calls),
        wrote_preferences=wrote_preferences,
        wrote_behaviors=wrote_behaviors,
        wrote_session_summary=wrote_session_summary,
        only_cursor=only_cursor,
    )


def render_content_prompt(
    conversation: str,
    extracted_content: str,
    memory_type: str,
    expected_keywords: list[str] = [],
) -> str:
    """渲染 Content Quality 评估 Prompt"""
    return CONTENT_QUALITY_PROMPT.format(
        conversation=conversation,
        extracted_content=extracted_content,
        memory_type=memory_type,
        expected_keywords=json.dumps(expected_keywords),
    )


def render_utilization_prompt(
    query: str,
    memory: str,
    answer_a: str,
    answer_b: str,
) -> str:
    """渲染 Utilization 评估 Prompt"""
    return UTILIZATION_PAIRWISE_PROMPT.format(
        query=query,
        memory=memory,
        answer_a=answer_a,
        answer_b=answer_b,
    )


def render_multi_turn_prompt(
    conversation_history: str,
    memory_evolution: str,
    current_response: str,
) -> str:
    """渲染 Multi-turn 评估 Prompt"""
    return MULTI_TURN_CONSISTENCY_PROMPT.format(
        conversation_history=conversation_history,
        memory_evolution=memory_evolution,
        current_response=current_response,
    )


__all__ = [
    "EXTRACTION_DECISION_PROMPT",
    "CONTENT_QUALITY_PROMPT",
    "UTILIZATION_PAIRWISE_PROMPT",
    "MULTI_TURN_CONSISTENCY_PROMPT",
    "render_extraction_prompt",
    "render_content_prompt",
    "render_utilization_prompt",
    "render_multi_turn_prompt",
]