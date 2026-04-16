"""领域层共享内核

包含所有领域共用的基础设施：
- 枚举类型
- 异常定义
- 值对象（如有）
"""

from app.domain.shared.enums import (
    ConversationStatus,
    DifficultyLevel,
    MasteryLevel,
    MemoryType,
    QuestionStatus,
    QuestionType,
    SessionStatus,
)

from app.domain.shared.exceptions import (
    ChatDomainException,
    ConversationNotFoundError,
    ConversationNotActiveError,
    DomainException,
    ExtractTaskNotFoundError,
    ExtractTaskNotReadyError,
    InvariantViolationError,
    InterviewDomainException,
    InterviewQuestionNotFoundError,
    InterviewSessionNotFoundError,
    InterviewSessionNotActiveError,
    MemoryDomainException,
    MemoryNotFoundError,
    MemoryExtractionError,
    MessageNotFoundError,
    NoQuestionsAvailableError,
    QuestionDomainException,
    QuestionNotFoundError,
    QuestionAlreadyExistsError,
    ClusterNotFoundError,
    ValidationError,
)

__all__ = [
    # 枚举
    "QuestionType",
    "MasteryLevel",
    "DifficultyLevel",
    "SessionStatus",
    "QuestionStatus",
    "MemoryType",
    "ConversationStatus",
    # 异常基类
    "DomainException",
    # 题库领域异常
    "QuestionDomainException",
    "QuestionNotFoundError",
    "QuestionAlreadyExistsError",
    "ExtractTaskNotFoundError",
    "ExtractTaskNotReadyError",
    "ClusterNotFoundError",
    # 模拟面试领域异常
    "InterviewDomainException",
    "InterviewSessionNotFoundError",
    "InterviewSessionNotActiveError",
    "InterviewQuestionNotFoundError",
    "NoQuestionsAvailableError",
    # 智能对话领域异常
    "ChatDomainException",
    "ConversationNotFoundError",
    "ConversationNotActiveError",
    "MessageNotFoundError",
    # 记忆领域异常
    "MemoryDomainException",
    "MemoryNotFoundError",
    "MemoryExtractionError",
    # 通用异常
    "ValidationError",
    "InvariantViolationError",
]