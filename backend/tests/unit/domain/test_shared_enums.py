"""领域共享枚举单元测试

验证枚举定义正确性和业务逻辑方法。
"""

import pytest

from app.domain.shared.enums import (
    ConversationStatus,
    DifficultyLevel,
    MasteryLevel,
    MemoryType,
    QuestionStatus,
    QuestionType,
    SessionStatus,
)


class TestQuestionType:
    """题目类型枚举测试"""

    def test_all_question_types_defined(self) -> None:
        """验证所有题目类型已定义"""
        expected_types = ["knowledge", "project", "behavioral", "scenario", "algorithm"]
        actual_types = [qt.value for qt in QuestionType]
        assert actual_types == expected_types

    def test_knowledge_requires_async_answer(self) -> None:
        """验证 knowledge 类型需要异步生成答案"""
        assert QuestionType.KNOWLEDGE.requires_async_answer() is True

    def test_scenario_requires_async_answer(self) -> None:
        """验证 scenario 类型需要异步生成答案"""
        assert QuestionType.SCENARIO.requires_async_answer() is True

    def test_algorithm_requires_async_answer(self) -> None:
        """验证 algorithm 类型需要异步生成答案"""
        assert QuestionType.ALGORITHM.requires_async_answer() is True

    def test_project_does_not_require_async_answer(self) -> None:
        """验证 project 类型不需要异步生成答案（熔断）"""
        assert QuestionType.PROJECT.requires_async_answer() is False

    def test_behavioral_does_not_require_async_answer(self) -> None:
        """验证 behavioral 类型不需要异步生成答案（熔断）"""
        assert QuestionType.BEHAVIORAL.requires_async_answer() is False

    def test_question_type_is_string_enum(self) -> None:
        """验证 QuestionType 是字符串枚举"""
        assert isinstance(QuestionType.KNOWLEDGE.value, str)
        assert QuestionType.KNOWLEDGE == "knowledge"


class TestMasteryLevel:
    """熟练度等级枚举测试"""

    def test_all_mastery_levels_defined(self) -> None:
        """验证所有熟练度等级已定义"""
        expected_levels = [0, 1, 2]
        actual_levels = [ml.value for ml in MasteryLevel]
        assert actual_levels == expected_levels

    def test_mastery_level_is_int_enum(self) -> None:
        """验证 MasteryLevel 是整数枚举"""
        assert isinstance(MasteryLevel.LEVEL_0.value, int)
        assert MasteryLevel.LEVEL_0 == 0

    def test_mastery_level_order(self) -> None:
        """验证熟练度等级顺序"""
        assert MasteryLevel.LEVEL_0 < MasteryLevel.LEVEL_1
        assert MasteryLevel.LEVEL_1 < MasteryLevel.LEVEL_2


class TestDifficultyLevel:
    """难度等级枚举测试"""

    def test_all_difficulty_levels_defined(self) -> None:
        """验证所有难度等级已定义"""
        expected_levels = ["easy", "medium", "hard"]
        actual_levels = [dl.value for dl in DifficultyLevel]
        assert actual_levels == expected_levels


class TestSessionStatus:
    """面试会话状态枚举测试"""

    def test_all_session_statuses_defined(self) -> None:
        """验证所有会话状态已定义"""
        expected_statuses = ["active", "paused", "completed"]
        actual_statuses = [ss.value for ss in SessionStatus]
        assert actual_statuses == expected_statuses


class TestQuestionStatus:
    """面试题目状态枚举测试"""

    def test_all_question_statuses_defined(self) -> None:
        """验证所有题目状态已定义"""
        expected_statuses = ["pending", "answering", "scored", "skipped"]
        actual_statuses = [qs.value for qs in QuestionStatus]
        assert actual_statuses == expected_statuses


class TestMemoryType:
    """记忆类型枚举测试"""

    def test_all_memory_types_defined(self) -> None:
        """验证所有记忆类型已定义"""
        expected_types = ["user_profile", "session_summary", "interview_insight"]
        actual_types = [mt.value for mt in MemoryType]
        assert actual_types == expected_types


class TestConversationStatus:
    """对话会话状态枚举测试"""

    def test_all_conversation_statuses_defined(self) -> None:
        """验证所有对话状态已定义"""
        expected_statuses = ["active", "archived"]
        actual_statuses = [cs.value for cs in ConversationStatus]
        assert actual_statuses == expected_statuses