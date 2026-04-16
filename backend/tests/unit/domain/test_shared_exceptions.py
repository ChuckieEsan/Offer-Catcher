"""领域共享异常单元测试

验证异常定义正确性和属性访问。
"""

import pytest

from domain.shared.exceptions import (
    ChatDomainException,
    ClusterNotFoundError,
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
    MemoryExtractionError,
    MemoryNotFoundError,
    MessageNotFoundError,
    NoQuestionsAvailableError,
    QuestionDomainException,
    QuestionNotFoundError,
    QuestionAlreadyExistsError,
    ValidationError,
)


class TestDomainException:
    """领域异常基类测试"""

    def test_basic_domain_exception(self) -> None:
        """验证基本异常属性"""
        exc = DomainException(message="Something went wrong", domain="test", code="TEST_ERROR")
        assert exc.message == "Something went wrong"
        assert exc.domain == "test"
        assert exc.code == "TEST_ERROR"

    def test_str_representation(self) -> None:
        """验证字符串表示"""
        exc = DomainException(message="Error", domain="test", code="TEST")
        assert str(exc) == "[test:TEST] Error"

    def test_default_code(self) -> None:
        """验证默认异常代码"""
        exc = DomainException(message="Error", domain="test")
        assert exc.code == "DOMAIN_ERROR"


class TestQuestionDomainExceptions:
    """题库领域异常测试"""

    def test_question_not_found_error(self) -> None:
        """验证题目不存在异常"""
        exc = QuestionNotFoundError(question_id="abc123")
        assert exc.question_id == "abc123"
        assert exc.domain == "question"
        assert exc.code == "QUESTION_NOT_FOUND"
        assert "abc123" in exc.message

    def test_question_already_exists_error(self) -> None:
        """验证题目已存在异常"""
        exc = QuestionAlreadyExistsError(question_id="abc123")
        assert exc.question_id == "abc123"
        assert exc.domain == "question"
        assert exc.code == "QUESTION_ALREADY_EXISTS"

    def test_extract_task_not_found_error(self) -> None:
        """验证提取任务不存在异常"""
        exc = ExtractTaskNotFoundError(task_id="task123")
        assert exc.task_id == "task123"
        assert exc.domain == "question"
        assert exc.code == "EXTRACT_TASK_NOT_FOUND"

    def test_extract_task_not_ready_error(self) -> None:
        """验证提取任务未就绪异常"""
        exc = ExtractTaskNotReadyError(task_id="task123", current_status="pending")
        assert exc.task_id == "task123"
        assert exc.current_status == "pending"
        assert "pending" in exc.message

    def test_cluster_not_found_error(self) -> None:
        """验证考点簇不存在异常"""
        exc = ClusterNotFoundError(cluster_id="cluster_001")
        assert exc.cluster_id == "cluster_001"
        assert exc.domain == "question"
        assert exc.code == "CLUSTER_NOT_FOUND"


class TestInterviewDomainExceptions:
    """模拟面试领域异常测试"""

    def test_interview_session_not_found_error(self) -> None:
        """验证面试会话不存在异常"""
        exc = InterviewSessionNotFoundError(session_id="session123")
        assert exc.session_id == "session123"
        assert exc.domain == "interview"
        assert exc.code == "SESSION_NOT_FOUND"

    def test_interview_session_not_active_error(self) -> None:
        """验证面试会话非活跃异常"""
        exc = InterviewSessionNotActiveError(session_id="session123", current_status="completed")
        assert exc.session_id == "session123"
        assert exc.current_status == "completed"
        assert "completed" in exc.message

    def test_interview_question_not_found_error(self) -> None:
        """验证面试题目不存在异常"""
        exc = InterviewQuestionNotFoundError(session_id="session123", question_index=5)
        assert exc.session_id == "session123"
        assert exc.question_index == 5

    def test_no_questions_available_error(self) -> None:
        """验证题库无可用题目异常"""
        exc = NoQuestionsAvailableError(company="字节跳动", position="后端开发")
        assert exc.company == "字节跳动"
        assert exc.position == "后端开发"


class TestChatDomainExceptions:
    """智能对话领域异常测试"""

    def test_conversation_not_found_error(self) -> None:
        """验证对话不存在异常"""
        exc = ConversationNotFoundError(conversation_id="conv123")
        assert exc.conversation_id == "conv123"
        assert exc.domain == "chat"
        assert exc.code == "CONVERSATION_NOT_FOUND"

    def test_conversation_not_active_error(self) -> None:
        """验证对话非活跃异常"""
        exc = ConversationNotActiveError(conversation_id="conv123", current_status="archived")
        assert exc.conversation_id == "conv123"
        assert exc.current_status == "archived"

    def test_message_not_found_error(self) -> None:
        """验证消息不存在异常"""
        exc = MessageNotFoundError(message_id="msg123")
        assert exc.message_id == "msg123"


class TestMemoryDomainExceptions:
    """记忆领域异常测试"""

    def test_memory_not_found_error(self) -> None:
        """验证记忆不存在异常"""
        exc = MemoryNotFoundError(memory_id="mem123")
        assert exc.memory_id == "mem123"
        assert exc.domain == "memory"

    def test_memory_extraction_error(self) -> None:
        """验证记忆提取失败异常"""
        exc = MemoryExtractionError(source_id="conv123", reason="LLM timeout")
        assert exc.source_id == "conv123"
        assert exc.reason == "LLM timeout"


class TestGenericExceptions:
    """通用异常测试"""

    def test_validation_error(self) -> None:
        """验证领域验证异常"""
        exc = ValidationError(message="Invalid mastery level", field="mastery_level")
        assert exc.field == "mastery_level"
        assert exc.domain == "validation"

    def test_validation_error_without_field(self) -> None:
        """验证无字段名的验证异常"""
        exc = ValidationError(message="Validation failed")
        assert exc.field is None

    def test_invariant_violation_error(self) -> None:
        """验证不变量 violation 异常"""
        exc = InvariantViolationError(message="Question count must be positive")
        assert exc.domain == "invariant"
        assert exc.code == "INARIANT_VIOLATION"


class TestExceptionHierarchy:
    """异常层级关系测试"""

    def test_question_exceptions_inherit_correctly(self) -> None:
        """验证题库异常继承关系"""
        exc = QuestionNotFoundError("q123")
        assert isinstance(exc, QuestionDomainException)
        assert isinstance(exc, DomainException)
        assert isinstance(exc, Exception)

    def test_interview_exceptions_inherit_correctly(self) -> None:
        """验证面试异常继承关系"""
        exc = InterviewSessionNotFoundError("s123")
        assert isinstance(exc, InterviewDomainException)
        assert isinstance(exc, DomainException)

    def test_chat_exceptions_inherit_correctly(self) -> None:
        """验证对话异常继承关系"""
        exc = ConversationNotFoundError("c123")
        assert isinstance(exc, ChatDomainException)
        assert isinstance(exc, DomainException)

    def test_memory_exceptions_inherit_correctly(self) -> None:
        """验证记忆异常继承关系"""
        exc = MemoryNotFoundError("m123")
        assert isinstance(exc, MemoryDomainException)
        assert isinstance(exc, DomainException)