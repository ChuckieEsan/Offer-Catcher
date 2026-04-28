"""记忆内容质量评估指标

使用 DeepEval G-Eval 评估提取的记忆内容质量。
"""

from typing import List, Optional, Union

from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCaseParams

from tests.memory.deepeval_config import DeepSeekJudgeModel


def get_default_judge_model() -> DeepSeekJudgeModel:
    """获取默认的 Judge 模型实例"""
    return DeepSeekJudgeModel()


DEFAULT_CONTENT_QUALITY_PARAMS = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
    LLMTestCaseParams.EXPECTED_OUTPUT,
]


class MemoryContentQualityMetric(GEval):
    """记忆内容质量评估

    评估提取的记忆内容是否：
    1. 完整 - 包含关键信息
    2. 准确 - 正确反映用户意图
    3. 结构化 - 符合格式规范
    4. 噪音过滤 - 排除无关信息

    仅在 Agent 写入记忆时使用此指标。
    """

    def __init__(
        self,
        name: Optional[str] = None,
        threshold: float = 0.6,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        evaluation_params: Optional[List[LLMTestCaseParams]] = None,
        criteria: Optional[str] = None,
        **kwargs,
    ):
        default_name = "Memory Content Quality"
        default_criteria = """
评估提取的记忆内容质量。

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
- preferences 是否包含偏好描述？
- behaviors 是否包含 Evidence？
- session_summary 是否包含 topics？

### 4. 噪音过滤 (noise_free)
- 是否过滤了无关信息？
- 是否包含情绪词/噪音词？
- 是否有冗余内容？

## 评分标准
- 高质量内容: 5分
- 内容基本可用但有改进空间: 3-4分
- 内容质量较差: 1-2分
"""

        super().__init__(
            name=name or default_name,
            criteria=criteria or default_criteria,
            evaluation_params=evaluation_params or DEFAULT_CONTENT_QUALITY_PARAMS,
            threshold=threshold,
            model=model or get_default_judge_model(),
            **kwargs,
        )


__all__ = [
    "MemoryContentQualityMetric",
]