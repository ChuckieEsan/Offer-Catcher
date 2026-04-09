"""面试 API - AI 模拟面试官接口

提供模拟面试的创建、进行、结束等功能。
"""

from typing import Optional
from fastapi import APIRouter, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.interview_agent import get_interview_manager
from app.models.interview_session import (
    InterviewSession,
    InterviewSessionCreate,
    AnswerSubmit,
    InterviewReport,
)
from app.utils.logger import logger

router = APIRouter(prefix="/interview", tags=["interview"])


def get_user_id(x_user_id: Optional[str] = Header(default="default_user")) -> str:
    """获取用户 ID"""
    return x_user_id or "default_user"


# ==================== Request/Response Models ====================

class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    company: str
    position: str
    status: str
    total_questions: int
    current_question_idx: int
    current_question: Optional[str] = None


class AnswerResponse(BaseModel):
    """回答响应"""
    type: str  # follow_up / next_question / completed
    message: str
    question_idx: Optional[int] = None
    question: Optional[str] = None


class HintResponse(BaseModel):
    """提示响应"""
    hint: str


# ==================== API Endpoints ====================

@router.post("/sessions", response_model=SessionResponse)
async def create_interview_session(
    request: InterviewSessionCreate,
    user_id: str = Depends(get_user_id),
):
    """创建面试会话

    创建一个新的模拟面试会话，AI 面试官会根据选择的公司和岗位出题。

    Args:
        request: 创建请求，包含公司、岗位、难度等

    Returns:
        会话信息，包含第一道题目
    """
    logger.info(f"Creating interview session: user={user_id}, company={request.company}, position={request.position}")

    manager = get_interview_manager()
    session = manager.create_session(user_id, request)

    current_question = session.get_current_question()

    return SessionResponse(
        session_id=session.session_id,
        company=session.company,
        position=session.position,
        status=session.status,
        total_questions=session.total_questions,
        current_question_idx=session.current_question_idx,
        current_question=current_question.question_text if current_question else None,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
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
    manager = get_interview_manager()
    session = manager.get_session(session_id)

    if not session:
        return {"error": "Session not found"}

    current_question = session.get_current_question()

    return SessionResponse(
        session_id=session.session_id,
        company=session.company,
        position=session.position,
        status=session.status,
        total_questions=session.total_questions,
        current_question_idx=session.current_question_idx,
        current_question=current_question.question_text if current_question else None,
    )


@router.post("/sessions/{session_id}/answer")
async def submit_answer(
    session_id: str,
    request: AnswerSubmit,
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

    manager = get_interview_manager()

    async def generate():
        try:
            for chunk in await manager.process_answer_stream(session_id, request.answer):
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
        }
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

    manager = get_interview_manager()

    async def generate():
        try:
            for chunk in await manager.get_hint_stream(session_id):
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
        }
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

    manager = get_interview_manager()
    result = await manager.skip_question(session_id)

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

    manager = get_interview_manager()
    session = manager.get_session(session_id)

    if session:
        session.status = "completed"
        session.ended_at = type('_', (), {'now': lambda: type('_', (), {})()})()
        session.ended_at.now = lambda: __import__('datetime').datetime.now()

    return {
        "message": "面试已结束",
        "session_id": session_id,
    }


@router.get("/sessions/{session_id}/report", response_model=InterviewReport)
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

    manager = get_interview_manager()
    report = manager.get_report(session_id)

    if not report:
        return {"error": "Report not available"}

    return report


__all__ = ["router"]