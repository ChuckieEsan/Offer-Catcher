"""Score API - 答案评分接口

对用户提交的答案进行 AI 评分。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.agents.scorer import get_scorer_agent
from app.models import ScoreResult
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/score", tags=["score"])


# ========== Request/Response Models ==========

class ScoreRequest(BaseModel):
    """评分请求"""
    question_id: str
    user_answer: str


# ========== API Endpoints ==========

@router.post("", response_model=ScoreResult)
async def score_answer(request: ScoreRequest):
    """评分答案

    对用户提交的答案进行评分，返回分数和反馈。
    """
    logger.info(f"Score answer: question_id={request.question_id}")

    scorer = get_scorer_agent()

    try:
        result = await scorer.score(
            question_id=request.question_id,
            user_answer=request.user_answer
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Score failed: {e}")
        raise HTTPException(status_code=500, detail=f"评分失败: {str(e)}")