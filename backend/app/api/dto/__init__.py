"""API DTO 定义

包含请求和响应的数据传输对象。
"""

from app.api.dto.question_dto import (
    QuestionCreateRequest,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdateRequest,
    BatchAnswersRequest,
    BatchAnswersResponse,
)
from app.api.dto.interview_dto import (
    InterviewQuestionResponse,
    InterviewSessionResponse,
    InterviewSessionListResponse,
    InterviewReportResponse,
    AnswerResponse,
    HintResponse,
    InterviewSessionCreateRequest,
    AnswerSubmitRequest,
)

__all__ = [
    "QuestionCreateRequest",
    "QuestionListResponse",
    "QuestionResponse",
    "QuestionUpdateRequest",
    "BatchAnswersRequest",
    "BatchAnswersResponse",
    "InterviewQuestionResponse",
    "InterviewSessionResponse",
    "InterviewSessionListResponse",
    "InterviewReportResponse",
    "AnswerResponse",
    "HintResponse",
    "InterviewSessionCreateRequest",
    "AnswerSubmitRequest",
]