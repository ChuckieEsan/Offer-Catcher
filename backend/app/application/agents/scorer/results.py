"""Scorer Agent 输出结果模型

Re-export ScoreResult from Domain layer.
遵循依赖倒置原则：Domain 层定义类型，Application 层 re-export。
"""

from app.domain.interview.aggregates import ScoreResult

__all__ = ["ScoreResult"]