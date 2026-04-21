"""面试领域聚合定义

包含面试领域的聚合根：
- InterviewSession: 试会话聚合根
- InterviewQuestion: 面试题目实体
- InterviewSessionCreate: 创建面试请求
- InterviewReport: 面试报告
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.shared.enums import DifficultyLevel, SessionStatus, QuestionStatus


class InterviewQuestion(BaseModel):
    """面试题目实体"""

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
        """回答题目"""
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
        """转换为数据库 payload 格式

        Returns:
            可 JSON 序列化的字典
        """
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
        """从数据库 payload 创建实例

        Args:
            payload: JSON 字典

        Returns:
            InterviewQuestion 实例
        """
        answered_at_str = payload.get("answered_at")
        answered_at = datetime.fromisoformat(answered_at_str) if answered_at_str else None

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
            answered_at=answered_at,
        )


class InterviewSession(BaseModel):
    """面试会话聚合根"""

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

    def get_current_question(self) -> Optional[InterviewQuestion]:
        """获取当前题目"""
        if 0 <= self.current_question_idx < len(self.questions):
            return self.questions[self.current_question_idx]
        return None

    def next_question(self) -> Optional[InterviewQuestion]:
        """进入下一题"""
        self.current_question_idx += 1
        self.updated_at = datetime.now()
        return self.get_current_question()

    def answer_current_question(self, user_answer: str, score: int, feedback: str) -> None:
        """回答当前题目"""
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

    def complete(self) -> None:
        """完成会话"""
        self.status = SessionStatus.COMPLETED
        self.ended_at = datetime.now()
        self.updated_at = datetime.now()

    def pause(self) -> None:
        """暂停会话"""
        self.status = SessionStatus.PAUSED
        self.updated_at = datetime.now()

    def resume(self) -> None:
        """恢复会话"""
        self.status = SessionStatus.ACTIVE
        self.updated_at = datetime.now()

    def add_question(self, question: InterviewQuestion) -> None:
        """添加题目"""
        self.questions.append(question)
        self.updated_at = datetime.now()

    @classmethod
    def create(
        cls,
        user_id: str,
        company: str,
        position: str,
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        total_questions: int = 10,
    ) -> "InterviewSession":
        """创建面试会话（工厂方法）

        Args:
            user_id: 用户 ID
            company: 公司名称
            position: 岗位名称
            difficulty: 难度设置
            total_questions: 题目总数

        Returns:
            新创建的 InterviewSession 实例
        """
        session_id = str(__import__("uuid").uuid4())
        return cls(
            session_id=session_id,
            user_id=user_id,
            company=company,
            position=position,
            difficulty=difficulty,
            total_questions=total_questions,
            status=SessionStatus.ACTIVE,
        )

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


class InterviewSessionCreate(BaseModel):
    """创建面试会话请求"""

    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(default="medium", description="难度设置")
    total_questions: int = Field(default=10, ge=1, le=50, description="题目总数")


class InterviewReport(BaseModel):
    """面试报告"""

    session_id: str
    company: str
    position: str
    total_questions: int
    answered_questions: int
    correct_count: int
    average_score: float
    duration_minutes: float
    overall_evaluation: str = Field(default="", description="综合评价")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    question_details: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "InterviewQuestion",
    "InterviewSession",
    "InterviewSessionCreate",
    "InterviewReport",
]