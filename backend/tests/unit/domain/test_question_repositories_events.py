"""题库领域 Repository Protocol 和事件单元测试

验证 Protocol 定义正确性和事件数据结构。
"""

import pytest
from datetime import datetime

from app.domain.question.repositories import (
    ClusterRepository,
    ExtractTaskRepository,
    QuestionRepository,
)
from app.domain.question.events import (
    AnswerGenerated,
    ClusterAssigned,
    ClusterCreated,
    ExtractConfirmed,
    MasteryLevelUpdated,
    QuestionCreated,
    QuestionDeleted,
)
from app.domain.question.aggregates import Question, Cluster, ExtractTask


class TestQuestionRepositoryProtocol:
    """QuestionRepository Protocol 测试

    Protocol 测试主要验证 Mock 类是否符合 Protocol 定义。
    """

    def test_mock_repository_satisfies_protocol(self) -> None:
        """验证 Mock 类满足 Protocol"""

        class MockQuestionRepository:
            """Mock 仓库，用于测试"""

            def __init__(self) -> None:
                self._questions: dict[str, Question] = {}

            def find_by_id(self, question_id: str) -> Question | None:
                return self._questions.get(question_id)

            def save(self, question: Question) -> None:
                self._questions[question.question_id] = question

            def delete(self, question_id: str) -> None:
                self._questions.pop(question_id, None)

            def search(
                self,
                query_vector: list[float],
                filter_conditions: dict | None = None,
                limit: int = 10,
            ) -> list[Question]:
                return list(self._questions.values())[:limit]

            def find_by_company_and_position(
                self,
                company: str,
                position: str,
                limit: int = 100,
            ) -> list[Question]:
                return [
                    q
                    for q in self._questions.values()
                    if q.company == company and q.position == position
                ][:limit]

            def find_all(self) -> list[Question]:
                return list(self._questions.values())

            def count(self) -> int:
                return len(self._questions)

            def exists(self, question_id: str) -> bool:
                return question_id in self._questions

        # Mock 可以直接使用，类型检查器会识别它为 QuestionRepository
        mock_repo = MockQuestionRepository()
        assert isinstance(mock_repo, QuestionRepository)  # runtime checkable

    def test_protocol_methods_defined(self) -> None:
        """验证 Protocol 定义了所有必要方法"""
        # 检查 Protocol 是否定义了预期的方法
        assert hasattr(QuestionRepository, "find_by_id")
        assert hasattr(QuestionRepository, "save")
        assert hasattr(QuestionRepository, "delete")
        assert hasattr(QuestionRepository, "search")
        assert hasattr(QuestionRepository, "find_by_company_and_position")
        assert hasattr(QuestionRepository, "find_all")
        assert hasattr(QuestionRepository, "count")
        assert hasattr(QuestionRepository, "exists")


class TestClusterRepositoryProtocol:
    """ClusterRepository Protocol 测试"""

    def test_protocol_methods_defined(self) -> None:
        """验证 Protocol 定义了所有必要方法"""
        assert hasattr(ClusterRepository, "find_by_id")
        assert hasattr(ClusterRepository, "save")
        assert hasattr(ClusterRepository, "delete")
        assert hasattr(ClusterRepository, "find_all")
        assert hasattr(ClusterRepository, "find_by_question_id")
        assert hasattr(ClusterRepository, "count")


class TestExtractTaskRepositoryProtocol:
    """ExtractTaskRepository Protocol 测试"""

    def test_protocol_methods_defined(self) -> None:
        """验证 Protocol 定义了所有必要方法"""
        assert hasattr(ExtractTaskRepository, "find_by_id")
        assert hasattr(ExtractTaskRepository, "save")
        assert hasattr(ExtractTaskRepository, "delete")
        assert hasattr(ExtractTaskRepository, "find_by_status")
        assert hasattr(ExtractTaskRepository, "find_pending_tasks")


class TestQuestionCreatedEvent:
    """QuestionCreated 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = QuestionCreated(
            question_id="q_001",
            question_type="knowledge",
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            core_entities=["RAG", "LLM"],
            requires_answer=True,
        )
        assert event.question_id == "q_001"
        assert event.question_type == "knowledge"
        assert event.requires_answer is True

    def test_event_has_timestamp(self) -> None:
        """验证事件有时间戳"""
        event = QuestionCreated(
            question_id="q_001",
            question_type="knowledge",
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
        )
        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)

    def test_to_dict(self) -> None:
        """验证转换为字典"""
        event = QuestionCreated(
            question_id="q_001",
            question_type="knowledge",
            question_text="什么是 RAG？",
            company="字节跳动",
            position="Agent 开发",
            core_entities=["RAG"],
        )
        data = event.to_dict()
        assert data["type"] == "QuestionCreated"
        assert data["question_id"] == "q_001"
        assert "occurred_at" in data


class TestAnswerGeneratedEvent:
    """AnswerGenerated 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = AnswerGenerated(
            question_id="q_001",
            answer="RAG 是检索增强生成技术...",
        )
        assert event.question_id == "q_001"
        assert event.answer == "RAG 是检索增强生成技术..."

    def test_to_dict(self) -> None:
        """验证转换为字典"""
        event = AnswerGenerated(question_id="q_001", answer="这是答案")
        data = event.to_dict()
        assert data["type"] == "AnswerGenerated"
        assert data["answer"] == "这是答案"


class TestQuestionDeletedEvent:
    """QuestionDeleted 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = QuestionDeleted(
            question_id="q_001",
            cluster_ids=["cluster_001", "cluster_002"],
        )
        assert event.question_id == "q_001"
        assert len(event.cluster_ids) == 2

    def test_empty_cluster_ids(self) -> None:
        """验证空 cluster_ids"""
        event = QuestionDeleted(question_id="q_001")
        assert event.cluster_ids == []


class TestClusterAssignedEvent:
    """ClusterAssigned 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = ClusterAssigned(
            cluster_id="cluster_001",
            question_ids=["q_001", "q_002", "q_003"],
        )
        assert event.cluster_id == "cluster_001"
        assert len(event.question_ids) == 3

    def test_to_dict(self) -> None:
        """验证转换为字典"""
        event = ClusterAssigned(cluster_id="cluster_001", question_ids=["q_001"])
        data = event.to_dict()
        assert data["type"] == "ClusterAssigned"
        assert data["cluster_id"] == "cluster_001"


class TestExtractConfirmedEvent:
    """ExtractConfirmed 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = ExtractConfirmed(
            task_id="task_001",
            company="字节跳动",
            position="Agent 开发",
            question_texts=["什么是 RAG？", "什么是 LLM？"],
        )
        assert event.task_id == "task_001"
        assert len(event.question_texts) == 2


class TestMasteryLevelUpdatedEvent:
    """MasteryLevelUpdated 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = MasteryLevelUpdated(
            question_id="q_001",
            old_level=0,
            new_level=1,
        )
        assert event.question_id == "q_001"
        assert event.old_level == 0
        assert event.new_level == 1


class TestClusterCreatedEvent:
    """ClusterCreated 事件测试"""

    def test_create_event(self) -> None:
        """验证事件创建"""
        event = ClusterCreated(
            cluster_id="cluster_001",
            cluster_name="RAG 技术",
            question_ids=["q_001", "q_002"],
        )
        assert event.cluster_id == "cluster_001"
        assert event.cluster_name == "RAG 技术"