"""Interview Domain Services - 接口定义

定义 Interview Domain 的领域服务接口（Protocol）和纯函数。
遵循依赖倒置原则：Domain 层只定义接口，Application 层实现。

接口列表：
- AnswerScorer: 答题评分器接口

纯函数（状态机逻辑）：
- calculate_new_level: 根据分数计算新的熟练度等级
"""

from typing import Protocol

from app.models import ScoreResult
from app.models.question import MasteryLevel


def calculate_new_level(current_level: MasteryLevel, score: int) -> MasteryLevel:
    """根据分数计算新的熟练度等级

    状态机规则：
    - LEVEL_0 -> LEVEL_2: score >= 85
    - LEVEL_0 -> LEVEL_1: score >= 60
    - LEVEL_1 -> LEVEL_2: score >= 85
    - LEVEL_2 保持不变
    - score < 60 保持当前等级

    Args:
        current_level: 当前熟练度等级
        score: 评分分数

    Returns:
        新的熟练度等级
    """
    if current_level == MasteryLevel.LEVEL_0:
        if score >= 85:
            return MasteryLevel.LEVEL_2
        elif score >= 60:
            return MasteryLevel.LEVEL_1
    elif current_level == MasteryLevel.LEVEL_1:
        if score >= 85:
            return MasteryLevel.LEVEL_2

    return current_level


class AnswerScorer(Protocol):
    """答题评分器接口

    由 ScorerAgent 实现，在 Application 层。
    """

    async def score(
        self,
        question_id: str,
        user_answer: str,
    ) -> ScoreResult:
        """对答案进行评分

        Args:
            question_id: 题目 ID
            user_answer: 用户提交的答案

        Returns:
            ScoreResult 包含评分和反馈
        """
        ...


__all__ = [
    "AnswerScorer",
    "calculate_new_level",
]