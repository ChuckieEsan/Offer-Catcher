"""题目应用服务

编排题目的 CRUD 用例，协调领域层和基础设施层。
作为应用层，负责：
- 调用仓库持久化聚合
- 缓存管理（查询缓存、失效策略）
- 答案生成（调用 AnswerSpecialist）
- 发布领域事件（未来）
"""

import asyncio
from typing import Optional

from app.domain.question.aggregates import Question, QuestionItem
from app.domain.question.repositories import QuestionRepository
from app.domain.shared.enums import MasteryLevel, QuestionType

from app.infrastructure.persistence.qdrant.question_repository import (
    get_question_repository,
)
from app.application.services.cache_service import (
    CacheApplicationService,
    CacheKeys,
    get_cache_service,
)
from app.application.agents.factory import get_answer_specialist
from app.application.agents.factory import get_answer_specialist
from app.infrastructure.common.logger import logger


class QuestionApplicationService:
    """题目应用服务

    编排题目的 CRUD 用例。通过依赖注入接收仓库实例，
    便于测试时使用 Mock。

    应用层职责：
    - 调用仓库持久化聚合
    - 缓存管理（查询缓存、失效策略）
    - 编排多个聚合的协作
    - 答案生成（调用 Agent）
    """

    def __init__(
        self,
        question_repo: Optional[QuestionRepository] = None,
        cache: Optional[CacheApplicationService] = None,
    ) -> None:
        """初始化应用服务

        Args:
            question_repo: Question 仓库（支持依赖注入）
            cache: 缓存服务（支持依赖注入）
        """
        self._question_repo = question_repo or get_question_repository()
        self._cache = cache or get_cache_service()

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

        # 失效缓存
        self._cache.invalidate_question()

        logger.info(
            f"Created question: {question.question_id}, "
            f"type={question_type.value}"
        )

        return question

    def get_question(self, question_id: str) -> Question | None:
        """获取题目（不带缓存）

        Args:
            question_id: 题目 ID

        Returns:
            Question 实例或 None
        """
        return self._question_repo.find_by_id(question_id)

    def get_question_with_cache(self, question_id: str) -> Question | None:
        """获取题目（带缓存防穿透）

        Args:
            question_id: 题目 ID

        Returns:
            Question 实例或 None
        """

        def fetch() -> dict | None:
            """获取数据并转换为可序列化的 dict"""
            question = self._question_repo.find_by_id(question_id)
            return question.to_payload() if question else None

        # 缓存返回 dict 或 None
        cached_dict = self._cache.get_question_item(question_id, fetch)

        if cached_dict is None:
            return None

        # 转换回 Question 对象
        return Question.from_payload(cached_dict)

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

        # 延迟双删：第一次删除缓存
        self._cache.invalidate_question(question_id)

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

        # 延迟双删：后台任务在 1 秒后再次删除
        asyncio.create_task(self._cache.invalidate_question_delayed(question_id))

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

        # 失效缓存
        self._cache.invalidate_question(question_id)

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
        """列出题目（不带缓存，带过滤和分页）

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
        # 获取所有数据
        all_questions = self._question_repo.find_all()

        # 内存过滤
        if company:
            all_questions = [q for q in all_questions if q.company == company]

        if position:
            all_questions = [q for q in all_questions if q.position == position]

        if question_type:
            all_questions = [
                q for q in all_questions
                if q.question_type == question_type
            ]

        if mastery_level is not None:
            all_questions = [
                q for q in all_questions
                if q.mastery_level == mastery_level
            ]

        if cluster_id:
            all_questions = [
                q for q in all_questions
                if cluster_id in q.cluster_ids
            ]

        if keyword:
            keyword_lower = keyword.lower()
            all_questions = [
                q for q in all_questions
                if keyword_lower in q.question_text.lower()
            ]

        # 计算总数和分页
        total = len(all_questions)
        start = (page - 1) * page_size
        end = start + page_size

        return all_questions[start:end], total

    def list_questions_with_cache(
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
        """列出题目（带缓存，带过滤和分页）

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
        # 构建过滤参数（用于缓存哈希）
        filter_params = {
            "company": company,
            "position": position,
            "question_type": question_type.value if question_type else None,
            "mastery_level": mastery_level.value if mastery_level else None,
            "cluster_id": cluster_id,
            "keyword": keyword,
        }

        def fetch() -> tuple[list[dict], int]:
            """获取数据并转换为可序列化的 dict"""
            questions, total = self.list_questions(
                company=company,
                position=position,
                question_type=question_type,
                mastery_level=mastery_level,
                cluster_id=cluster_id,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
            # 转换为 dict 以便缓存序列化
            dicts = [q.to_payload() for q in questions]
            return dicts, total

        # 通过缓存获取（返回 tuple[list[dict], int]）
        all_dicts, total = self._cache.get_questions_list(filter_params, fetch)

        # 转换回 Question 对象
        all_questions = [Question.from_payload(d) for d in all_dicts]

        # 分页处理
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

    def regenerate_answer(
        self,
        question_id: str,
        preview: bool = True,
    ) -> str | None:
        """重新生成答案

        Args:
            question_id: 题目 ID
            preview: 是否仅预览（不保存）

        Returns:
            生成的新答案，或 None（题目不存在）
        """
        # 获取题目
        question = self._question_repo.find_by_id(question_id)
        if not question:
            logger.warning(f"Question not found for regenerate: {question_id}")
            return None

        # 构建 QuestionItem（用于 AnswerSpecialist）
        question_item = QuestionItem(
            question_id=question.question_id,
            question_text=question.question_text,
            company=question.company,
            position=question.position,
            question_type=question.question_type,
            core_entities=question.core_entities,
            metadata=question.metadata,
        )

        # 调用 AnswerSpecialist 生成答案
        specialist = get_answer_specialist()
        answer = specialist.generate_answer(question_item)

        # 仅当 preview=False 时才保存
        if not preview:
            question.update_answer(answer)
            self._question_repo.update_answer(question_id, answer)

            # 失效缓存
            self._cache.invalidate_question(question_id)

            logger.info(f"Answer saved for question: {question_id}")

        return answer

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