"""Interview Domain - Domain Events

定义面试领域的领域事件。
用于跨聚合通信和最终一致性。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class InterviewStarted:
    """面试开始事件"""

    session_id: str
    user_id: str
    company: str
    position: str
    difficulty: str
    total_questions: int
    occurred_at: datetime


@dataclass
class InterviewEnded:
    """面试结束事件

    面试结束时触发，用于：
    - MemoryAgent 提取面试洞察
    - 更新用户长期记忆
    """

    session_id: str
    user_id: str
    company: str
    position: str
    correct_count: int
    average_score: float
    duration_minutes: float
    occurred_at: datetime


@dataclass
class QuestionAnswered:
    """题目回答事件"""

    session_id: str
    question_id: str
    score: int
    occurred_at: datetime


@dataclass
class QuestionSkipped:
    """题目跳过事件"""

    session_id: str
    question_id: str
    occurred_at: datetime


__all__ = [
    "InterviewStarted",
    "InterviewEnded",
    "QuestionAnswered",
    "QuestionSkipped",
]