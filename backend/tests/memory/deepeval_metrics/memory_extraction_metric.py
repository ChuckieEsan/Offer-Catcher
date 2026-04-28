"""记忆提取正确性评估指标

使用 DeepEval G-Eval 框架评估记忆提取决策：
1. should_remember: 是否应该记忆
2. memory_type_correct: 记忆类型是否正确
3. temporary_constraint_detected: 临时约束识别
4. dedup_correct: 去重判断
"""

from typing import List, Optional, Union

from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCaseParams

from tests.memory.deepeval_config import DeepSeekJudgeModel


def get_default_judge_model() -> DeepSeekJudgeModel:
    """获取默认的 Judge 模型实例"""
    return DeepSeekJudgeModel()


# 默认评估参数
DEFAULT_EXTRACTION_PARAMS = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
    LLMTestCaseParams.EXPECTED_OUTPUT,
    LLMTestCaseParams.CONTEXT,
]

DEFAULT_TYPE_PARAMS = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
    LLMTestCaseParams.EXPECTED_OUTPUT,
]

DEFAULT_TEMP_CONSTRAINT_PARAMS = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
]

DEFAULT_DEDUP_PARAMS = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
    LLMTestCaseParams.CONTEXT,
]


class MemoryExtractionCorrectnessMetric(GEval):
    """记忆提取正确性综合评估

    评估 Memory Agent 的整体决策质量，包括：
    - 是否应该写入记忆
    - 记忆类型是否正确
    - 临时约束是否正确处理
    - 去重判断是否正确

    使用 G-Eval 的 Chain-of-Thought 评分机制。
    """

    def __init__(
        self,
        name: Optional[str] = None,
        threshold: float = 0.7,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        evaluation_params: Optional[List[LLMTestCaseParams]] = None,
        criteria: Optional[str] = None,
        **kwargs,
    ):
        # 默认指标名称和评估标准
        default_name = "Memory Extraction Correctness"
        default_criteria = """
评估 Memory Agent 的记忆提取决策是否正确。

## 评估标准

### 1. 应该记忆判断
用户是否表达了值得长期记忆的信息？

**应该写入长期记忆**：
- 用户明确说"以后都..."、"我喜欢..."、"我不喜欢..."
- 用户给出反馈"这个太.../不够..."
- 深度讨论某个话题（>=3轮追问）
- 观察到重复的行为模式（>=2次相同序列）

**不应写入长期记忆**：
- 临时约束："这次"、"这道题"、"先"、"现在"
- 闲聊、确认、感谢
- 隐私信息、密码、个人信息
- 简单问答（<=2轮）

### 2. 记忆类型判断
- preferences: 用户主动表达的偏好、反馈
- behaviors: 观察到的重复行为模式（需>=2次）
- session_summary: 深度讨论或有结论的对话

### 3. 临时约束识别
包含"这次"、"这道题"、"先"、"后面再"等临时性表达时，
不应写入长期记忆。

### 4. 去重判断
新内容与已有内容语义相似时应跳过：
- "简洁" ≈ "简洁直接" ≈ "不要太长"

## 评分标准
- 5分: 所有判断完全正确
- 4分: 大部分正确，有轻微偏差
- 3分: 基本正确但有明显问题
- 2分: 多处判断错误
- 1分: 完全错误
"""

        super().__init__(
            name=name or default_name,
            criteria=criteria or default_criteria,
            evaluation_params=evaluation_params or DEFAULT_EXTRACTION_PARAMS,
            threshold=threshold,
            model=model or get_default_judge_model(),
            **kwargs,
        )


class MemoryTypeMetric(GEval):
    """记忆类型评估指标

    专门评估记忆类型分类是否正确。
    """

    def __init__(
        self,
        name: Optional[str] = None,
        threshold: float = 0.8,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        evaluation_params: Optional[List[LLMTestCaseParams]] = None,
        criteria: Optional[str] = None,
        **kwargs,
    ):
        default_name = "Memory Type Classification"
        default_criteria = """
评估 Memory Agent 的记忆类型分类是否正确。

## 记忆类型定义

### preferences（偏好）
- 用户主动表达的偏好、反馈或要求
- 包含"我喜欢"、"我不喜欢"、"以后都"等显式表达
- 包含负向反馈"不要这样"、"不准确"

### behaviors（行为模式）
- 系统观察到的用户行为模式
- 必须观察到至少 2 次重复序列才能写入
- 例如：多次"原理→实现"的追问序列

### session_summary（会话摘要）
- 有检索价值的深度讨论
- 需要>=3轮追问或有明确结论
- 技术问题解决方案

### none（不应记忆）
- 临时约束、闲聊、隐私等不应写入的内容

## 评分标准
- 正确分类: 5分
- 类型相近但细分错误: 3分
- 类型完全错误: 1分
"""

        super().__init__(
            name=name or default_name,
            criteria=criteria or default_criteria,
            evaluation_params=evaluation_params or DEFAULT_TYPE_PARAMS,
            threshold=threshold,
            model=model or get_default_judge_model(),
            **kwargs,
        )


class TemporaryConstraintMetric(GEval):
    """临时约束识别指标

    专门评估是否正确识别临时约束。
    """

    def __init__(
        self,
        name: Optional[str] = None,
        threshold: float = 0.85,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        evaluation_params: Optional[List[LLMTestCaseParams]] = None,
        criteria: Optional[str] = None,
        **kwargs,
    ):
        default_name = "Temporary Constraint Detection"
        default_criteria = """
评估是否正确识别临时约束，不应写入长期记忆。

## 临时约束特征

### 关键词识别
- "这次"、"这道题"、"本次"
- "先"、"先给我"、"先简短"
- "后面再"、"之后再"
- "现在"、"今天"

### 判断标准
如果用户表达包含以上关键词，且意图是：
- 当前单次生效
- 稍后会改变
- 情境限定

则应识别为临时约束，不写入长期记忆。

## 评分标准
- 正确识别临时约束且不写入: 5分
- 识别但仍然写入（严重错误）: 1分
- 未识别临时约束: 视情况评分
"""

        super().__init__(
            name=name or default_name,
            criteria=criteria or default_criteria,
            evaluation_params=evaluation_params or DEFAULT_TEMP_CONSTRAINT_PARAMS,
            threshold=threshold,
            model=model or get_default_judge_model(),
            **kwargs,
        )


class DeduplicationMetric(GEval):
    """去重判断指标

    专门评估去重判断是否正确。
    """

    def __init__(
        self,
        name: Optional[str] = None,
        threshold: float = 0.75,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        evaluation_params: Optional[List[LLMTestCaseParams]] = None,
        criteria: Optional[str] = None,
        **kwargs,
    ):
        default_name = "Deduplication Correctness"
        default_criteria = """
评估去重判断是否正确。

## 去重判断标准

### 偏好去重
- "简洁" ≈ "简洁直接" ≈ "不要太长" ≈ "回答简短"
- "详细" ≈ "深入" ≈ "完整解释"
- "代码示例" ≈ "给代码" ≈ "代码演示"

### 摘要去重
- 同一话题的追问不产生新摘要
- 只是确认或感谢不产生新摘要
- 只是细化细节不产生新摘要

### 判断方法
比较新内容与已有记忆的语义相似度：
- 高相似度（语义等价）→ 应跳过
- 有差异（新信息）→ 应写入

## 评分标准
- 正确去重或正确写入: 5分
- 应去重但写入: 1分
- 不确定情况: 3分
"""

        super().__init__(
            name=name or default_name,
            criteria=criteria or default_criteria,
            evaluation_params=evaluation_params or DEFAULT_DEDUP_PARAMS,
            threshold=threshold,
            model=model or get_default_judge_model(),
            **kwargs,
        )


__all__ = [
    "MemoryExtractionCorrectnessMetric",
    "MemoryTypeMetric",
    "TemporaryConstraintMetric",
    "DeduplicationMetric",
]