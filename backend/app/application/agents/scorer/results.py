"""Scorer Agent 输出结果模型

定义 Scorer Agent 的结构化输出。
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.domain.shared.enums import MasteryLevel


class ScoreResult(BaseModel):
    """打分结果模型

    Scorer Agent 输出的结构化结果，包含评分和反馈。
    """

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    standard_answer: Optional[str] = Field(default=None, description="标准答案")
    user_answer: str = Field(description="用户提交的答案")
    score: int = Field(ge=0, le=100, description="评分 0-100")
    mastery_level: MasteryLevel = Field(description="熟练度等级")
    strengths: list[str] = Field(default_factory=list, description="答案优点")
    improvements: list[str] = Field(default_factory=list, description="改进建议")
    feedback: str = Field(description="综合反馈")


__all__ = [
    "ScoreResult",
]