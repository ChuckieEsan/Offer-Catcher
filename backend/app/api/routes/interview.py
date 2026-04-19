"""面试 API - AI 模拟面试官接口

提供模拟面试的创建、进行、结束等功能。

注意：当前使用 InterviewManager（内存会话），后续将迁移到 InterviewApplicationService（PostgreSQL 持久化）。
"""

from typing import Optional
from fastapi import APIRouter, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.application.agents.factory import get_interview_agent
from app.domain.interview.aggregates import InterviewSession, InterviewSessionCreate, InterviewReport
from app.api.dto.interview_dto import (
    InterviewSessionResponse,
    InterviewSessionListResponse,
    InterviewReportResponse,
    InterviewSessionCreateRequest,
    AnswerSubmitRequest,
    AnswerResponse,
    HintResponse,
    InterviewQuestionResponse,
)
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/interview", tags=["interview"])


def get_user_id(x_user_id: Optional[str] = Header(default="default_user")) -> str:
    """获取用户 ID"""
    return x_user_id or "default_user"


# ==================== 内部转换函数 ====================


def _session_to_response(session: InterviewSession) -> InterviewSessionResponse:
    """将 InterviewSession 模型转换为响应 DTO"""
    current_question = session.get_current_question()
    return InterviewSessionResponse(
        session_id=session.session_id,
        company=session.company,
        position=session.position,
        difficulty=session.difficulty,
        total_questions=session.total_questions,
        status=session.status,
        current_question_idx=session.current_question_idx,
        correct_count=session.correct_count,
        total_score=session.total_score,
        started_at=session.started_at,
        ended_at=session.ended_at,
        current_question=InterviewQuestionResponse(
            question_id=current_question.question_id,
            question_text=current_question.question_text,
            question_type=current_question.question_type,
            difficulty=current_question.difficulty,
            knowledge_points=current_question.knowledge_points,
            user_answer=current_question.user_answer,
            score=current_question.score,
            feedback=current_question.feedback,
            status=current_question.status,
        ) if current_question else None,
    )


def _report_to_response(report: InterviewReport) -> InterviewReportResponse:
    """将 InterviewReport 模型转换为响应 DTO"""
    return InterviewReportResponse(
        session_id=report.session_id,
        company=report.company,
        position=report.position,
        total_questions=report.total_questions,
        answered_questions=report.answered_questions,
        correct_count=report.correct_count,
        average_score=report.average_score,
        duration_minutes=report.duration_minutes,
        overall_evaluation=report.overall_evaluation,
        strengths=report.strengths,
        weaknesses=report.weaknesses,
        knowledge_gaps=report.knowledge_gaps,
        recommendations=report.recommendations,
        question_details=report.question_details,
    )


# ==================== API 端点 ====================


@router.post("/sessions", response_model=InterviewSessionResponse)
async def create_interview_session(
    request: InterviewSessionCreateRequest,
    user_id: str = Depends(get_user_id),
):
    """创建面试会话

    创建一个新的模拟面试会话，AI 面试官会根据选择的公司和岗位出题。

    Args:
        request: 创建请求，包含公司、岗位、难度等

    Returns:
        会话信息，包含第一道题目
    """
    logger.info(
        f"Creating interview session: user={user_id}, "
        f"company={request.company}, position={request.position}"
    )

    # 转换 DTO 到模型（兼容 InterviewManager）
    create_request = InterviewSessionCreate(
        company=request.company,
        position=request.position,
        difficulty=request.difficulty,
        total_questions=request.total_questions,
    )

    agent = get_interview_agent()
    session = agent.create_session(user_id, create_request)

    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=InterviewSessionResponse)
async def get_interview_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
):
    """获取面试会话详情

    Args:
        session_id: 会话 ID

    Returns:
        会话详情
    """
    logger.info(f"Get interview session: session={session_id}, user={user_id}")

    agent = get_interview_agent()
    session = agent.get_session(session_id)

    if not session:
        return {"error": "Session not found"}

    return _session_to_response(session)


@router.post("/sessions/{session_id}/answer")
async def submit_answer(
    session_id: str,
    request: AnswerSubmitRequest,
    user_id: str = Depends(get_user_id),
):
    """提交回答（流式响应）

    提交用户对当前题目的回答，AI 面试官会流式输出评估和追问。

    Args:
        session_id: 会话 ID
        request: 回答内容

    Returns:
        SSE 流式响应
    """
    logger.info(f"Submit answer: session={session_id}, answer_length={len(request.answer)}")

    agent = get_interview_agent()

    async def generate():
        try:
            async for chunk in agent.process_answer_stream(session_id, request.answer):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/hint")
async def request_hint(
    session_id: str,
    user_id: str = Depends(get_user_id),
):
    """请求提示（流式响应）

    当用户不知道如何回答时，可以请求提示。

    Args:
        session_id: 会话 ID

    Returns:
        SSE 流式响应
    """
    logger.info(f"Request hint: session={session_id}")

    agent = get_interview_agent()

    async def generate():
        try:
            async for chunk in agent.get_hint_stream(session_id):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/skip", response_model=AnswerResponse)
async def skip_question(
    session_id: str,
    user_id: str = Depends(get_user_id),
):
    """跳过当前题目

    跳过当前题目，进入下一题。

    Args:
        session_id: 会话 ID

    Returns:
        下一题信息
    """
    logger.info(f"Skip question: session={session_id}")

    agent = get_interview_agent()
    result = await agent.skip_question(session_id)

    return AnswerResponse(
        type=result.get("type", "next_question"),
        message=result.get("message", ""),
        question_idx=result.get("question_idx"),
        question=result.get("question"),
    )


@router.post("/sessions/{session_id}/end")
async def end_interview(
    session_id: str,
    user_id: str = Depends(get_user_id),
):
    """结束面试

    提前结束面试，生成报告。

    Args:
        session_id: 会话 ID

    Returns:
        结束信息
    """
    logger.info(f"End interview: session={session_id}")

    agent = get_interview_agent()
    session = agent.get_session(session_id)

    if session:
        session.status = "completed"
        session.ended_at = __import__("datetime").datetime.now()

    return {
        "message": "面试已结束",
        "session_id": session_id,
    }


@router.get("/sessions/{session_id}/report", response_model=InterviewReportResponse)
async def get_interview_report(
    session_id: str,
    user_id: str = Depends(get_user_id),
):
    """获取面试报告

    面试结束后，获取详细的面试报告。

    Args:
        session_id: 会话 ID

    Returns:
        面试报告
    """
    logger.info(f"Get interview report: session={session_id}")

    agent = get_interview_agent()
    report = agent.get_report(session_id)

    if not report:
        return {"error": "Report not available"}

    return _report_to_response(report)


__all__ = ["router"]