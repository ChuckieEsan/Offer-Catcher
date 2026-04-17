"""面试应用服务

编排面试会话的用例，协调领域层和基础设施层。
作为应用层，负责：
- 调用仓库持久化聚合
- 调用 Agent 进行题目预加载和评分
- 编排面试流程
"""

import uuid
from typing import Optional

from app.domain.interview.aggregates import InterviewSession, InterviewQuestion
from app.domain.interview.repositories import InterviewSessionRepository
from app.domain.shared.enums import DifficultyLevel, SessionStatus, QuestionStatus

from app.infrastructure.persistence.postgres.interview_session_repository import (
    get_interview_session_repository,
)
from app.infrastructure.common.logger import logger


class InterviewApplicationService:
    """面试应用服务

    编排面试会话的创建、进行、结束等用例。
    通过依赖注入接收仓库实例，便于测试时使用 Mock。

    应用层职责：
    - 调用仓库持久化会话
    - 调用 Agent 进行题目预加载
    - 编排面试流程（创建、回答、评分、结束）
    """

    def __init__(
        self,
        session_repo: Optional[InterviewSessionRepository] = None,
    ) -> None:
        """初始化应用服务

        Args:
            session_repo: InterviewSession 仓库（支持依赖注入）
        """
        self._session_repo = session_repo or get_interview_session_repository()

    def create_session(
        self,
        user_id: str,
        company: str,
        position: str,
        difficulty: str = "medium",
        total_questions: int = 10,
    ) -> InterviewSession:
        """创建面试会话

        Args:
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            difficulty: 难度设置
            total_questions: 题目总数

        Returns:
            创建的 InterviewSession 实例
        """
        session_id = str(uuid.uuid4())
        difficulty_level = DifficultyLevel(difficulty)

        session = InterviewSession.create(
            session_id=session_id,
            user_id=user_id,
            company=company,
            position=position,
            difficulty=difficulty_level,
            total_questions=total_questions,
        )

        # 持久化会话（题目由 Agent 预加载）
        self._session_repo.save(session)

        logger.info(
            f"Created interview session: {session_id}, "
            f"user={user_id}, company={company}, position={position}"
        )

        return session

    def get_session(self, session_id: str, user_id: str) -> InterviewSession | None:
        """获取面试会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            InterviewSession 实例或 None
        """
        return self._session_repo.find_by_id(session_id, user_id)

    def list_sessions(
        self,
        user_id: str,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list[InterviewSession]:
        """列出用户的面试会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            status: 状态过滤（可选）

        Returns:
            InterviewSession 列表
        """
        return self._session_repo.find_by_user(user_id, limit, status)

    def add_question(
        self,
        session_id: str,
        user_id: str,
        question: InterviewQuestion,
    ) -> InterviewSession | None:
        """添加题目到会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            question: 面试题目

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.add_question(question)
        self._session_repo.save(session)

        logger.info(f"Added question to session: {session_id}")
        return session

    def answer_question(
        self,
        session_id: str,
        user_id: str,
        user_answer: str,
        score: int,
        feedback: str,
    ) -> InterviewSession | None:
        """回答当前题目

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            user_answer: 用户回答
            score: 评分
            feedback: AI 反馈

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.answer_current_question(user_answer, score, feedback)
        self._session_repo.save(session)

        logger.info(
            f"Answered question in session: {session_id}, "
            f"score={score}, idx={session.current_question_idx}"
        )
        return session

    def skip_question(
        self,
        session_id: str,
        user_id: str,
    ) -> InterviewSession | None:
        """跳过当前题目

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.skip_current_question()
        self._session_repo.save(session)

        logger.info(f"Skipped question in session: {session_id}")
        return session

    def next_question(
        self,
        session_id: str,
        user_id: str,
    ) -> InterviewQuestion | None:
        """进入下一题

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            下一题或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        next_q = session.next_question()
        self._session_repo.save(session)

        logger.info(f"Moved to next question in session: {session_id}")
        return next_q

    def pause_session(
        self,
        session_id: str,
        user_id: str,
    ) -> InterviewSession | None:
        """暂停会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.pause()
        self._session_repo.save(session)

        logger.info(f"Paused session: {session_id}")
        return session

    def resume_session(
        self,
        session_id: str,
        user_id: str,
    ) -> InterviewSession | None:
        """恢复会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.resume()
        self._session_repo.save(session)

        logger.info(f"Resumed session: {session_id}")
        return session

    def complete_session(
        self,
        session_id: str,
        user_id: str,
    ) -> InterviewSession | None:
        """完成会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            更新后的 InterviewSession 实例或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.complete()
        self._session_repo.save(session)

        logger.info(f"Completed session: {session_id}")
        return session

    def get_report(
        self,
        session_id: str,
        user_id: str,
    ) -> dict | None:
        """获取面试报告

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            面试报告字典或 None
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        # 计算统计数据
        answered_questions = [q for q in session.questions if q.is_answered()]
        scored_questions = [q for q in session.questions if q.score is not None]

        report = {
            "session_id": session.session_id,
            "company": session.company,
            "position": session.position,
            "total_questions": session.total_questions,
            "answered_questions": len(answered_questions),
            "correct_count": session.correct_count,
            "average_score": session.calculate_average_score(),
            "duration_minutes": session.calculate_duration_minutes(),
            "overall_evaluation": "",
            "strengths": [],
            "weaknesses": [],
            "knowledge_gaps": [],
            "recommendations": [],
            "question_details": [q.to_payload() for q in session.questions],
        }

        logger.info(f"Generated report for session: {session_id}")
        return report

    def delete_session(
        self,
        session_id: str,
        user_id: str,
    ) -> bool:
        """删除会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            是否成功删除
        """
        session = self._session_repo.find_by_id(session_id, user_id)
        if session is None:
            logger.warning(f"Session not found for deletion: {session_id}")
            return False

        self._session_repo.delete(session_id, user_id)
        logger.info(f"Deleted session: {session_id}")
        return True


# 单例获取函数
_interview_service: Optional[InterviewApplicationService] = None


def get_interview_service() -> InterviewApplicationService:
    """获取面试应用服务单例"""
    global _interview_service
    if _interview_service is None:
        _interview_service = InterviewApplicationService()
    return _interview_service


__all__ = [
    "InterviewApplicationService",
    "get_interview_service",
]