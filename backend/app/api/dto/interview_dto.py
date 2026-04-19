"""Interview API DTO

定义面试相关的请求和响应数据传输对象。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ========== 响应模型 ==========


class InterviewQuestionResponse(BaseModel):
    """面试题目响应"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    question_type: str = Field(description="题目类型")
    difficulty: str = Field(description="难度")
    knowledge_points: list[str] = Field(default_factory=list, description="知识点")
    user_answer: Optional[str] = Field(default=None, description="用户回答")
    score: Optional[int] = Field(default=None, ge=0, le=100, description="评分")
    feedback: Optional[str] = Field(default=None, description="AI反馈")
    status: str = Field(description="题目状态")


class InterviewSessionResponse(BaseModel):
    """面试会话响应"""

    session_id: str = Field(description="会话唯一标识")
    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(description="难度设置")
    total_questions: int = Field(description="题目总数")
    status: str = Field(description="会话状态")
    current_question_idx: int = Field(description="当前题目索引")
    correct_count: int = Field(description="答对数量")
    total_score: int = Field(description="总分")
    started_at: datetime = Field(description="开始时间")
    ended_at: Optional[datetime] = Field(default=None, description="结束时间")
    current_question: Optional[InterviewQuestionResponse] = Field(
        default=None, description="当前题目"
    )


class InterviewSessionListResponse(BaseModel):
    """面试会话列表响应"""

    items: list[InterviewSessionResponse]
    total: int = Field(description="总数")


class InterviewReportResponse(BaseModel):
    """面试报告响应"""

    session_id: str = Field(description="会话 ID")
    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    total_questions: int = Field(description="题目总数")
    answered_questions: int = Field(description="已回答数量")
    correct_count: int = Field(description="答对数量")
    average_score: float = Field(description="平均分")
    duration_minutes: float = Field(description="面试时长（分钟）")
    overall_evaluation: str = Field(default="", description="综合评价")
    strengths: list[str] = Field(default_factory=list, description="优势")
    weaknesses: list[str] = Field(default_factory=list, description="薄弱点")
    knowledge_gaps: list[str] = Field(default_factory=list, description="知识盲区")
    recommendations: list[str] = Field(default_factory=list, description="改进建议")
    question_details: list[dict[str, Any]] = Field(
        default_factory=list, description="题目详情"
    )


class AnswerResponse(BaseModel):
    """回答响应"""

    type: str = Field(description="响应类型: follow_up/next_question/completed")
    message: str = Field(description="消息内容")
    question_idx: Optional[int] = Field(default=None, description="题目索引")
    question: Optional[str] = Field(default=None, description="题目文本")


class HintResponse(BaseModel):
    """提示响应"""

    hint: str = Field(description="提示内容")


# ========== 请求模型 ==========


class InterviewSessionCreateRequest(BaseModel):
    """创建面试会话请求"""

    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(default="medium", description="难度设置")
    total_questions: int = Field(default=10, ge=1, le=50, description="题目总数")


class InterviewSessionCreate(BaseModel):
    """创建面试会话模型（内部使用）"""

    company: str = Field(description="目标公司")
    position: str = Field(description="目标岗位")
    difficulty: str = Field(default="medium", description="难度设置")
    total_questions: int = Field(default=10, ge=1, le=50, description="题目总数")


class AnswerSubmitRequest(BaseModel):
    """提交回答请求"""

    answer: str = Field(description="用户回答")


class AnswerSubmit(BaseModel):
    """提交回答模型（内部使用）"""

    answer: str = Field(description="用户回答")


class InterviewReport(BaseModel):
    """面试报告模型"""

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
    "InterviewQuestionResponse",
    "InterviewSessionResponse",
    "InterviewSessionListResponse",
    "InterviewReportResponse",
    "AnswerResponse",
    "HintResponse",
    "InterviewSessionCreateRequest",
    "InterviewSessionCreate",
    "AnswerSubmitRequest",
    "AnswerSubmit",
    "InterviewReport",
]