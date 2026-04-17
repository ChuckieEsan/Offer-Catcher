"""面试领域聚合定义

包含面试领域的聚合根：
- InterviewSession: 面试会话聚合根
- InterviewQuestion: 面试题目实体

聚合根是聚合的入口点，外部只能通过聚合根访问聚合内部对象。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.shared.enums import DifficultyLevel, SessionStatus, QuestionStatus


class InterviewQuestion(BaseModel):
    """面试题目实体

    记录面试过程中的一道题目及其回答情况。
    属于 InterviewSession 聚合，通过聚合根访问。

    Attributes:
        question_id: 关联题库中的题目 ID
        question_text: 题目文本
        question_type: 题目类型
        difficulty: 难度
        knowledge_points: 考察的知识点
        user_answer: 用户回答
        score: 评分 0-100
        feedback: AI 反馈
        follow_ups: 追问列表
        hints_given: 已给出的提示
        status: 状态
        answered_at: 回答时间
    """

    question_id: str = Field(description="关联题库中的题目 ID")
    question_text: str = Field(description="题目文本")
    question_type: str = Field(default="knowledge", description="题目类型")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM, description="难度")
    knowledge_points: list[str] = Field(default_factory=list, description="考察的知识点")

    user_answer: Optional[str] = Field(default=None, description="用户回答")
    score: Optional[int] = Field(default=None, ge=0, le=100, description="评分")
    feedback: Optional[str] = Field(default=None, description="AI 反馈")

    follow_ups: list[str] = Field(default_factory=list, description="追问列表")
    current_follow_up_idx: int = Field(default=0, description="当前追问索引")
    hints_given: list[str] = Field(default_factory=list, description="已给出的提示")

    status: QuestionStatus = Field(default=QuestionStatus.PENDING, description="状态")
    answered_at: Optional[datetime] = Field(default=None, description="回答时间")

    def answer(self, user_answer: str, score: int, feedback: str) -> None:
        """回答题目

        Args:
            user_answer: 用户回答
            score: 评分
            feedback: AI 反馈
        """
        self.user_answer = user_answer
        self.score = score
        self.feedback = feedback
        self.status = QuestionStatus.SCORED
        self.answered_at = datetime.now()

    def skip(self) -> None:
        """跳过题目"""
        self.status = QuestionStatus.SKIPPED
        self.answered_at = datetime.now()

    def add_hint(self, hint: str) -> None:
        """添加提示"""
        self.hints_given.append(hint)

    def add_follow_up(self, follow_up: str) -> None:
        """添加追问"""
        self.follow_ups.append(follow_up)

    def is_answered(self) -> bool:
        """是否已回答"""
        return self.status in (QuestionStatus.SCORED, QuestionStatus.SKIPPED)

    def to_payload(self) -> dict[str, Any]:
        """转换为存储 payload"""
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "difficulty": self.difficulty.value,
            "knowledge_points": self.knowledge_points,
            "user_answer": self.user_answer,
            "score": self.score,
            "feedback": self.feedback,
            "follow_ups": self.follow_ups,
            "current_follow_up_idx": self.current_follow_up_idx,
            "hints_given": self.hints_given,
            "status": self.status.value,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "InterviewQuestion":
        """从 payload 恢复实体"""
        return cls(
            question_id=payload["question_id"],
            question_text=payload["question_text"],
            question_type=payload.get("question_type", "knowledge"),
            difficulty=DifficultyLevel(payload.get("difficulty", "medium")),
            knowledge_points=payload.get("knowledge_points", []),
            user_answer=payload.get("user_answer"),
            score=payload.get("score"),
            feedback=payload.get("feedback"),
            follow_ups=payload.get("follow_ups", []),
            current_follow_up_idx=payload.get("current_follow_up_idx", 0),
            hints_given=payload.get("hints_given", []),
            status=QuestionStatus(payload.get("status", "pending")),
            answered_at=datetime.fromisoformat(payload["answered_at"]) if payload.get("answered_at") else None,
        )


class InterviewSession(BaseModel):
    """面试会话聚合根

    记录一次完整的模拟面试会话，是面试领域的核心聚合根。
    所有字段修改必须通过 InterviewSession 的方法进行，保证业务规则一致性。

    聚合内规则：
    - session_id 创建后不可变
    - 题目状态变更必须通过聚合根方法
    - 统计数据由聚合根计算，不外部设置

    Attributes:
        session_id: 会话唯一标识
        user_id: 用户 ID
        company: 目标公司
        position: 目标岗位
        difficulty: 难度设置
        status: 会话状态
        questions: 题目列表
        current_question_idx: 当前题目索引
        total_questions: 题目总数
        correct_count: 答对数量
        total_score: 总分
        started_at: 开始时间
        ended_at: 结束时间
        created_at: 创建时间
        updated_at: 更新时间
    """

    session_id: str = Field(description="会话唯一标识")
    user_id: str = Field(description="用户 ID")

    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM, description="难度设置")
    total_questions: int = Field(default=10, description="题目总数")

    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="会话状态")

    questions: list[InterviewQuestion] = Field(default_factory=list, description="题目列表")
    current_question_idx: int = Field(default=0, description="当前题目索引")

    correct_count: int = Field(default=0, description="答对数量")
    total_score: int = Field(default=0, description="总分")

    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    ended_at: Optional[datetime] = Field(default=None, description="结束时间")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    @classmethod
    def create(
        cls,
        session_id: str,
        user_id: str,
        company: str,
        position: str,
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        total_questions: int = 10,
    ) -> "InterviewSession":
        """创建面试会话（工厂方法）

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            difficulty: 难度设置
            total_questions: 题目总数

        Returns:
            InterviewSession 实例
        """
        return cls(
            session_id=session_id,
            user_id=user_id,
            company=company,
            position=position,
            difficulty=difficulty,
            total_questions=total_questions,
        )

    def add_question(self, question: InterviewQuestion) -> None:
        """添加题目

        Args:
            question: 面试题目实体
        """
        self.questions.append(question)
        self.updated_at = datetime.now()

    def get_current_question(self) -> Optional[InterviewQuestion]:
        """获取当前题目"""
        if 0 <= self.current_question_idx < len(self.questions):
            return self.questions[self.current_question_idx]
        return None

    def next_question(self) -> Optional[InterviewQuestion]:
        """进入下一题

        Returns:
            下一题，如果已结束返回 None
        """
        self.current_question_idx += 1
        self.updated_at = datetime.now()
        return self.get_current_question()

    def answer_current_question(
        self,
        user_answer: str,
        score: int,
        feedback: str,
    ) -> None:
        """回答当前题目

        Args:
            user_answer: 用户回答
            score: 评分
            feedback: AI 反馈
        """
        current = self.get_current_question()
        if current:
            current.answer(user_answer, score, feedback)
            self.total_score += score
            if score >= 60:
                self.correct_count += 1
            self.updated_at = datetime.now()

    def skip_current_question(self) -> None:
        """跳过当前题目"""
        current = self.get_current_question()
        if current:
            current.skip()
            self.updated_at = datetime.now()

    def pause(self) -> None:
        """暂停会话"""
        if self.status != SessionStatus.ACTIVE:
            raise ValueError(f"Cannot pause from status: {self.status}")
        self.status = SessionStatus.PAUSED
        self.updated_at = datetime.now()

    def resume(self) -> None:
        """恢复会话"""
        if self.status != SessionStatus.PAUSED:
            raise ValueError(f"Cannot resume from status: {self.status}")
        self.status = SessionStatus.ACTIVE
        self.updated_at = datetime.now()

    def complete(self) -> None:
        """完成会话"""
        self.status = SessionStatus.COMPLETED
        self.ended_at = datetime.now()
        self.updated_at = datetime.now()

    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status == SessionStatus.COMPLETED or self.current_question_idx >= self.total_questions

    def calculate_average_score(self) -> float:
        """计算平均分"""
        scored_questions = [q for q in self.questions if q.score is not None]
        if not scored_questions:
            return 0.0
        return sum(q.score for q in scored_questions) / len(scored_questions)

    def calculate_duration_minutes(self) -> float:
        """计算面试时长（分钟）"""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() / 60
        return (datetime.now() - self.started_at).total_seconds() / 60

    def to_payload(self) -> dict[str, Any]:
        """转换为存储 payload"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "company": self.company,
            "position": self.position,
            "difficulty": self.difficulty.value,
            "total_questions": self.total_questions,
            "status": self.status.value,
            "questions": [q.to_payload() for q in self.questions],
            "current_question_idx": self.current_question_idx,
            "correct_count": self.correct_count,
            "total_score": self.total_score,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "InterviewSession":
        """从 payload 恢复聚合"""
        return cls(
            session_id=payload["session_id"],
            user_id=payload["user_id"],
            company=payload["company"],
            position=payload["position"],
            difficulty=DifficultyLevel(payload.get("difficulty", "medium")),
            total_questions=payload.get("total_questions", 10),
            status=SessionStatus(payload.get("status", "active")),
            questions=[InterviewQuestion.from_payload(q) for q in payload.get("questions", [])],
            current_question_idx=payload.get("current_question_idx", 0),
            correct_count=payload.get("correct_count", 0),
            total_score=payload.get("total_score", 0),
            started_at=datetime.fromisoformat(payload["started_at"]),
            ended_at=datetime.fromisoformat(payload["ended_at"]) if payload.get("ended_at") else None,
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )


__all__ = [
    "InterviewQuestion",
    "InterviewSession",
]