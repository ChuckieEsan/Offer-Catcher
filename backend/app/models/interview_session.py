"""面试会话数据模型

用于 AI 模拟面试官功能的数据结构定义。
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    """面试题目记录

    记录面试过程中的一道题目及其回答情况。

    Attributes:
        question_id: 关联题库中的题目 ID
        question_text: 题目文本
        question_type: 题目类型（knowledge/project/behavioral/scenario/algorithm）
        difficulty: 难度（easy/medium/hard）
        knowledge_points: 考察的知识点
        user_answer: 用户回答
        score: 评分 0-100
        feedback: AI 反馈
        follow_ups: 追问列表
        hints_given: 已给出的提示
        status: 状态（pending/answering/scored/skipped）
        answered_at: 回答时间
    """

    question_id: str = Field(description="关联题库中的题目 ID")
    question_text: str = Field(description="题目文本")
    question_type: str = Field(default="knowledge", description="题目类型")
    difficulty: str = Field(default="medium", description="难度")
    knowledge_points: List[str] = Field(default_factory=list, description="考察的知识点")

    # 用户回答
    user_answer: Optional[str] = Field(default=None, description="用户回答")
    score: Optional[int] = Field(default=None, ge=0, le=100, description="评分")
    feedback: Optional[str] = Field(default=None, description="AI 反馈")

    # 追问相关
    follow_ups: List[str] = Field(default_factory=list, description="追问列表")
    current_follow_up_idx: int = Field(default=0, description="当前追问索引")
    hints_given: List[str] = Field(default_factory=list, description="已给出的提示")

    # 状态
    status: str = Field(default="pending", description="状态")
    answered_at: Optional[datetime] = Field(default=None, description="回答时间")


class InterviewSession(BaseModel):
    """面试会话

    记录一次完整的模拟面试会话。

    Attributes:
        session_id: 会话唯一标识
        user_id: 用户 ID
        company: 目标公司
        position: 目标岗位
        difficulty: 难度设置
        status: 会话状态（active/paused/completed）

        questions: 题目列表
        current_question_idx: 当前题目索引

        statistics: 面试统计
        started_at: 开始时间
        ended_at: 结束时间
        created_at: 创建时间
        updated_at: 更新时间
    """

    session_id: str = Field(description="会话唯一标识，UUID")
    user_id: str = Field(description="用户 ID")

    # 面试配置
    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(default="medium", description="难度设置")
    total_questions: int = Field(default=10, description="题目总数")

    # 状态
    status: str = Field(default="active", description="会话状态")

    # 题目
    questions: List[InterviewQuestion] = Field(default_factory=list, description="题目列表")
    current_question_idx: int = Field(default=0, description="当前题目索引")

    # 统计
    correct_count: int = Field(default=0, description="答对数量")
    total_score: int = Field(default=0, description="总分")

    # 时间
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    ended_at: Optional[datetime] = Field(default=None, description="结束时间")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    def get_current_question(self) -> Optional[InterviewQuestion]:
        """获取当前题目"""
        if 0 <= self.current_question_idx < len(self.questions):
            return self.questions[self.current_question_idx]
        return None

    def is_completed(self) -> bool:
        """检查面试是否已完成"""
        return self.status == "completed" or self.current_question_idx >= self.total_questions

    def calculate_average_score(self) -> float:
        """计算平均分"""
        scored_questions = [q for q in self.questions if q.score is not None]
        if not scored_questions:
            return 0.0
        return sum(q.score for q in scored_questions) / len(scored_questions)


class InterviewSessionCreate(BaseModel):
    """创建面试会话请求"""

    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(default="medium", description="难度设置")
    total_questions: int = Field(default=10, ge=1, le=50, description="题目总数")


class AnswerSubmit(BaseModel):
    """提交回答请求"""

    answer: str = Field(description="用户回答")


class InterviewReport(BaseModel):
    """面试报告

    面试结束后生成的详细报告。

    Attributes:
        session_id: 会话 ID
        company: 目标公司
        position: 目标岗位
        total_questions: 题目总数
        answered_questions: 已回答数量
        correct_count: 答对数量
        average_score: 平均分
        duration_minutes: 面试时长（分钟）

        strengths: 用户优势
        weaknesses: 薄弱点
        knowledge_gaps: 知识盲区
        recommendations: 改进建议

        question_details: 题目详情
    """

    session_id: str
    company: str
    position: str

    # 统计
    total_questions: int
    answered_questions: int
    correct_count: int
    average_score: float
    duration_minutes: float

    # 分析
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    knowledge_gaps: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

    # 详情
    question_details: List[dict] = Field(default_factory=list)


__all__ = [
    "InterviewQuestion",
    "InterviewSession",
    "InterviewSessionCreate",
    "AnswerSubmit",
    "InterviewReport",
]