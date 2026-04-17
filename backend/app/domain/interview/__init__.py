"""面试领域模块

包含面试会话相关的聚合根、仓库接口和业务规则。

领域对象：
- InterviewSession: 面试会话聚合根
- InterviewQuestion: 面试题目实体

仓库接口：
- InterviewSessionRepository: 会话持久化接口
"""

from app.domain.interview.aggregates import InterviewQuestion, InterviewSession
from app.domain.interview.repositories import InterviewSessionRepository

__all__ = [
    "InterviewQuestion",
    "InterviewSession",
    "InterviewSessionRepository",
]