"""领域层异常定义

所有领域共用的异常类型，遵循 DDD 分层架构原则。
领域异常用于表达业务规则 violations，而非技术错误。
"""

from typing import Optional


class DomainException(Exception):
    """领域异常基类

    所有领域层异常都应继承此基类。
    区别于技术异常（如网络错误、数据库错误），领域异常表达业务规则 violation。

    Attributes:
        message: 异常消息
        domain: 所属领域名称（如 question, interview, chat, memory）
        code: 异常代码，用于错误分类
    """

    def __init__(
        self,
        message: str,
        domain: str = "unknown",
        code: Optional[str] = None,
    ) -> None:
        self.message = message
        self.domain = domain
        self.code = code or "DOMAIN_ERROR"
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.domain}:{self.code}] {self.message}"


# ============ 题库领域异常 ============


class QuestionDomainException(DomainException):
    """题库领域异常基类"""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message, domain="question", code=code)


class QuestionNotFoundError(QuestionDomainException):
    """题目不存在异常"""

    def __init__(self, question_id: str) -> None:
        super().__init__(
            message=f"Question not found: {question_id}",
            code="QUESTION_NOT_FOUND",
        )
        self.question_id = question_id


class QuestionAlreadyExistsError(QuestionDomainException):
    """题目已存在异常（幂等性检查时触发）"""

    def __init__(self, question_id: str) -> None:
        super().__init__(
            message=f"Question already exists: {question_id}",
            code="QUESTION_ALREADY_EXISTS",
        )
        self.question_id = question_id


class ExtractTaskNotFoundError(QuestionDomainException):
    """提取任务不存在异常"""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Extract task not found: {task_id}",
            code="EXTRACT_TASK_NOT_FOUND",
        )
        self.task_id = task_id


class ExtractTaskNotReadyError(QuestionDomainException):
    """提取任务未就绪异常（状态不对时触发）"""

    def __init__(self, task_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Extract task {task_id} is not ready, current status: {current_status}",
            code="EXTRACT_TASK_NOT_READY",
        )
        self.task_id = task_id
        self.current_status = current_status


class ClusterNotFoundError(QuestionDomainException):
    """考点簇不存在异常"""

    def __init__(self, cluster_id: str) -> None:
        super().__init__(
            message=f"Cluster not found: {cluster_id}",
            code="CLUSTER_NOT_FOUND",
        )
        self.cluster_id = cluster_id


# ============ 模拟面试领域异常 ============


class InterviewDomainException(DomainException):
    """模拟面试领域异常基类"""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message, domain="interview", code=code)


class InterviewSessionNotFoundError(InterviewDomainException):
    """面试会话不存在异常"""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"Interview session not found: {session_id}",
            code="SESSION_NOT_FOUND",
        )
        self.session_id = session_id


class InterviewSessionNotActiveError(InterviewDomainException):
    """面试会话非活跃状态异常"""

    def __init__(self, session_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Interview session {session_id} is not active, current status: {current_status}",
            code="SESSION_NOT_ACTIVE",
        )
        self.session_id = session_id
        self.current_status = current_status


class InterviewQuestionNotFoundError(InterviewDomainException):
    """面试题目不存在异常（会话内的题目）"""

    def __init__(self, session_id: str, question_index: int) -> None:
        super().__init__(
            message=f"Interview question not found in session {session_id} at index {question_index}",
            code="INTERVIEW_QUESTION_NOT_FOUND",
        )
        self.session_id = session_id
        self.question_index = question_index


class NoQuestionsAvailableError(InterviewDomainException):
    """题库无可用题目异常"""

    def __init__(self, company: str, position: str) -> None:
        super().__init__(
            message=f"No questions available for company '{company}' and position '{position}'",
            code="NO_QUESTIONS_AVAILABLE",
        )
        self.company = company
        self.position = position


# ============ 智能对话领域异常 ============


class ChatDomainException(DomainException):
    """智能对话领域异常基类"""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message, domain="chat", code=code)


class ConversationNotFoundError(ChatDomainException):
    """对话不存在异常"""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            message=f"Conversation not found: {conversation_id}",
            code="CONVERSATION_NOT_FOUND",
        )
        self.conversation_id = conversation_id


class ConversationNotActiveError(ChatDomainException):
    """对话非活跃状态异常"""

    def __init__(self, conversation_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Conversation {conversation_id} is not active, current status: {current_status}",
            code="CONVERSATION_NOT_ACTIVE",
        )
        self.conversation_id = conversation_id
        self.current_status = current_status


class MessageNotFoundError(ChatDomainException):
    """消息不存在异常"""

    def __init__(self, message_id: str) -> None:
        super().__init__(
            message=f"Message not found: {message_id}",
            code="MESSAGE_NOT_FOUND",
        )
        self.message_id = message_id


# ============ 记忆领域异常 ============


class MemoryDomainException(DomainException):
    """记忆领域异常基类"""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message, domain="memory", code=code)


class MemoryNotFoundError(MemoryDomainException):
    """记忆不存在异常"""

    def __init__(self, memory_id: str) -> None:
        super().__init__(
            message=f"Memory not found: {memory_id}",
            code="MEMORY_NOT_FOUND",
        )
        self.memory_id = memory_id


class MemoryExtractionError(MemoryDomainException):
    """记忆提取失败异常"""

    def __init__(self, source_id: str, reason: str) -> None:
        super().__init__(
            message=f"Memory extraction failed for source {source_id}: {reason}",
            code="MEMORY_EXTRACTION_ERROR",
        )
        self.source_id = source_id
        self.reason = reason


# ============ 通用领域异常 ============


class ValidationError(DomainException):
    """领域验证异常

    用于表达业务规则验证失败，而非数据格式验证。
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message, domain="validation", code="VALIDATION_ERROR")
        self.field = field


class InvariantViolationError(DomainException):
    """不变量 violation 异常

    用于表达聚合内部一致性规则被破坏。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, domain="invariant", code="INARIANT_VIOLATION")


__all__ = [
    # 基类
    "DomainException",
    # 题库领域
    "QuestionDomainException",
    "QuestionNotFoundError",
    "QuestionAlreadyExistsError",
    "ExtractTaskNotFoundError",
    "ExtractTaskNotReadyError",
    "ClusterNotFoundError",
    # 模拟面试领域
    "InterviewDomainException",
    "InterviewSessionNotFoundError",
    "InterviewSessionNotActiveError",
    "InterviewQuestionNotFoundError",
    "NoQuestionsAvailableError",
    # 智能对话领域
    "ChatDomainException",
    "ConversationNotFoundError",
    "ConversationNotActiveError",
    "MessageNotFoundError",
    # 记忆领域
    "MemoryDomainException",
    "MemoryNotFoundError",
    "MemoryExtractionError",
    # 通用
    "ValidationError",
    "InvariantViolationError",
]