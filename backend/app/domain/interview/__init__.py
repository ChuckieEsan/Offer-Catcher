"""面试领域模块

包含面试会话相关的聚合根、仓库接口和业务规则。

领域对象：
- InterviewSession: 面试会话聚合根
- InterviewQuestion: 面试题目实体

仓库接口：
- InterviewSessionRepository: 会话持久化接口

领域事件：
- InterviewStarted: 面试开始事件
- InterviewEnded: 面试结束事件
"""

from app.domain.interview.aggregates import InterviewQuestion, InterviewSession
from app.domain.interview.repositories import InterviewSessionRepository
from app.domain.interview.events import (
    InterviewStarted,
    InterviewEnded,
    QuestionAnswered,
    QuestionSkipped,
)

__all__ = [
    # Aggregates
    "InterviewQuestion",
    "InterviewSession",
    # Repository Protocol
    "InterviewSessionRepository",
    # Events
    "InterviewStarted",
    "InterviewEnded",
    "QuestionAnswered",
    "QuestionSkipped",
]