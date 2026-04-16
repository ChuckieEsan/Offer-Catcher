"""题目应用服务

编排题目的 CRUD 用例，协调领域层和基础设施层。
作为应用层，负责：
- 调用仓库持久化聚合
- 发布领域事件（未来）
- 事务边界管理
"""

from typing import Optional

from app.domain.question.aggregates import Question
from app.domain.question.repositories import QuestionRepository
from app.domain.shared.enums import MasteryLevel, QuestionType

from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.infrastructure.common.logger import logger


class QuestionApplicationService:
    """题目应用服务

    编排题目的 CRUD 用例。通过依赖注入接收仓库实例，
    便于测试时使用 Mock。

    应用层职责：
    - 调用仓库持久化聚合
    - 编排多个聚合的协作
    - 发布领域事件
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
    ) -> None:
        """初始化应用服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
        """
        self._question_repo = question_repo or get_question_repository()

    def create_question(
        self,
        question_text: str,
        company: str,
        position: str,
        question_type: QuestionType,
        core_entities: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Question:
        """创建题目

        Args:
            question_text: 题目文本
            company: 公司名称
            position: 岗位名称
            question_type: 题目类型
            core_entities: 知识点列表
            metadata: 元数据

        Returns:
            创建的 Question 实例
        """
        # 使用领域工厂方法创建聚合
        question = Question.create(
            question_text=question_text,
            company=company,
            position=position,
            question_type=question_type,
            core_entities=core_entities,
            metadata=metadata,
        )

        # 持久化聚合
        self._question_repo.save(question)

        # 发布领域事件（未来实现）
        # self._event_publisher.publish(QuestionCreated(...))

        logger.info(
            f"Created question: {question.question_id}, "
            f"type={question_type.value}, requires_answer={question.requires_async_answer()}"
        )

        return question

    def get_question(self, question_id: str) -> Question | None:
        """获取题目

        Args:
            question_id: 题目 ID

        Returns:
            Question 实例或 None
        """
        return self._question_repo.find_by_id(question_id)

    def update_question(
        self,
        question_id: str,
        question_text: Optional[str] = None,
        answer: Optional[str] = None,
        mastery_level: Optional[MasteryLevel] = None,
        core_entities: Optional[list[str]] = None,
    ) -> Question | None:
        """更新题目

        Args:
            question_id: 题目 ID
            question_text: 新题目文本（如果变化，会重新计算 embedding）
            answer: 新答案
            mastery_level: 新熟练度
            core_entities: 新知识点列表

        Returns:
            更新后的 Question 实例或 None（不存在）
        """
        # 获取聚合
        question = self._question_repo.find_by_id(question_id)
        if not question:
            logger.warning(f"Question not found: {question_id}")
            return None

        # 更新字段
        if answer is not None:
            question.update_answer(answer)
            self._question_repo.update_answer(question_id, answer)

        if mastery_level is not None:
            question.update_mastery(mastery_level)
            self._question_repo.update_mastery(question_id, mastery_level)

        if core_entities is not None:
            question.core_entities = core_entities
            self._question_repo.save(question)

        # 如果题目文本变化，需要重新计算 embedding
        if question_text is not None and question_text != question.question_text:
            self._question_repo.update_with_reembedding(question, question_text)
            question.question_text = question_text

        logger.info(f"Updated question: {question_id}")
        return question

    def delete_question(self, question_id: str) -> bool:
        """删除题目

        Args:
            question_id: 题目 ID

        Returns:
            是否成功删除
        """
        # 检查是否存在
        question = self._question_repo.find_by_id(question_id)
        if not question:
            logger.warning(f"Question not found for deletion: {question_id}")
            return False

        # 删除
        self._question_repo.delete(question_id)

        # 发布领域事件（未来实现）
        # self._event_publisher.publish(QuestionDeleted(question_id, question.cluster_ids))

        logger.info(f"Deleted question: {question_id}")
        return True

    def list_questions(
        self,
        company: Optional[str] = None,
        position: Optional[str] = None,
        question_type: Optional[QuestionType] = None,
        mastery_level: Optional[MasteryLevel] = None,
        cluster_id: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Question], int]:
        """列出题目（带过滤和分页）

        Args:
            company: 公司过滤
            position: 岗位过滤
            question_type: 题目类型过滤
            mastery_level: 熟练度过滤
            cluster_id: 考点簇过滤
            keyword: 关键词过滤（内存过滤）
            page: 页码
            page_size: 每页数量

        Returns:
            (题目列表, 总数)
        """
        # 构建过滤条件
        filter_conditions = {}
        if company:
            filter_conditions["company"] = company
        if position:
            filter_conditions["position"] = position
        if question_type:
            filter_conditions["question_type"] = question_type.value
        if mastery_level is not None:
            filter_conditions["mastery_level"] = mastery_level.value
        if cluster_id:
            filter_conditions["cluster_ids"] = [cluster_id]

        # 获取所有符合条件的数据
        if company and position:
            all_questions = self._question_repo.find_by_company_and_position(
                company, position, limit=10000
            )
        else:
            all_questions = self._question_repo.find_all()

        # 内存过滤（关键词和其他条件）
        if keyword:
            keyword_lower = keyword.lower()
            all_questions = [
                q for q in all_questions
                if keyword_lower in q.question_text.lower()
            ]

        if question_type and not filter_conditions.get("question_type"):
            all_questions = [
                q for q in all_questions
                if q.question_type == question_type
            ]

        if mastery_level is not None and not filter_conditions.get("mastery_level"):
            all_questions = [
                q for q in all_questions
                if q.mastery_level == mastery_level
            ]

        if cluster_id and not filter_conditions.get("cluster_ids"):
            all_questions = [
                q for q in all_questions
                if cluster_id in q.cluster_ids
            ]

        # 计算总数和分页
        total = len(all_questions)
        start = (page - 1) * page_size
        end = start + page_size

        return all_questions[start:end], total

    def get_batch_answers(self, question_ids: list[str]) -> dict[str, str | None]:
        """批量获取题目答案

        Args:
            question_ids: 题目 ID 列表

        Returns:
            question_id -> answer 的映射
        """
        answers: dict[str, str | None] = {}
        for question_id in question_ids:
            question = self._question_repo.find_by_id(question_id)
            answers[question_id] = question.answer if question else None
        return answers

    def count_questions(self) -> int:
        """统计题目总数"""
        return self._question_repo.count()


# 单例获取函数
_question_service: Optional[QuestionApplicationService] = None


def get_question_service() -> QuestionApplicationService:
    """获取题目应用服务单例"""
    global _question_service
    if _question_service is None:
        _question_service = QuestionApplicationService()
    return _question_service


__all__ = [
    "QuestionApplicationService",
    "get_question_service",
]