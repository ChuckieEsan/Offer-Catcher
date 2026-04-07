"""Questions API - 题目管理接口

提供题目的 CRUD 操作。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from app.db.qdrant_client import get_qdrant_manager
from app.agents.answer_specialist import get_answer_specialist
from app.models.schemas import QdrantQuestionPayload, SearchResult
from app.utils.logger import logger

router = APIRouter(prefix="/questions", tags=["questions"])


# ========== Request/Response Models ==========

class QuestionListResponse(BaseModel):
    """题目列表响应"""
    items: List[QdrantQuestionPayload]
    total: int
    page: int
    page_size: int


class QuestionUpdateRequest(BaseModel):
    """题目更新请求"""
    question_text: Optional[str] = None
    question_answer: Optional[str] = None
    mastery_level: Optional[int] = None
    core_entities: Optional[List[str]] = None


class RegenerateResponse(BaseModel):
    """重新生成答案响应"""
    question_answer: str


# ========== API Endpoints ==========

@router.get("", response_model=QuestionListResponse)
async def list_questions(
    company: Optional[str] = Query(None, description="公司过滤"),
    position: Optional[str] = Query(None, description="岗位过滤"),
    question_type: Optional[str] = Query(None, description="题目类型过滤"),
    mastery_level: Optional[int] = Query(None, description="熟练度过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取题目列表

    支持按公司、岗位、类型、熟练度过滤。
    """
    logger.info(f"List questions: company={company}, page={page}")

    qdrant = get_qdrant_manager()
    all_questions = qdrant.scroll_all(limit=10000)

    # 应用过滤
    filtered = all_questions
    if company:
        filtered = [q for q in filtered if q.company == company]
    if position:
        filtered = [q for q in filtered if q.position == position]
    if question_type:
        filtered = [q for q in filtered if q.question_type == question_type]
    if mastery_level is not None:
        filtered = [q for q in filtered if q.mastery_level == mastery_level]

    total = len(filtered)

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    return QuestionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{question_id}", response_model=QdrantQuestionPayload)
async def get_question(question_id: str):
    """获取单个题目"""
    qdrant = get_qdrant_manager()
    question = qdrant.get_question(question_id)

    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    return question


@router.put("/{question_id}", response_model=QdrantQuestionPayload)
async def update_question(question_id: str, request: QuestionUpdateRequest):
    """更新题目

    如果更新了题目文本，会重新计算 embedding。
    """
    logger.info(f"Update question: {question_id}")

    qdrant = get_qdrant_manager()

    # 检查题目是否存在
    existing = qdrant.get_question(question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 如果更新了题目文本，需要重新计算 embedding
    if request.question_text and request.question_text != existing.question_text:
        qdrant.update_question_with_reembedding(
            question_id=question_id,
            company=existing.company,
            position=existing.position,
            question_text=request.question_text,
            question_answer=request.question_answer,
            mastery_level=request.mastery_level,
        )
    else:
        # 普通更新
        qdrant.update_question(
            question_id=question_id,
            question_text=request.question_text,
            question_answer=request.question_answer,
            mastery_level=request.mastery_level,
            core_entities=request.core_entities,
        )

    return qdrant.get_question(question_id)


@router.delete("/{question_id}")
async def delete_question(question_id: str):
    """删除题目"""
    logger.info(f"Delete question: {question_id}")

    qdrant = get_qdrant_manager()
    qdrant.delete_question(question_id)

    return {"success": True}


@router.post("/{question_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_answer(question_id: str):
    """重新生成答案

    调用 LLM 重新生成标准答案。
    """
    logger.info(f"Regenerate answer: {question_id}")

    qdrant = get_qdrant_manager()
    question = qdrant.get_question(question_id)

    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 调用 Answer Specialist 生成答案
    specialist = get_answer_specialist()
    answer = specialist.generate_answer(question)

    # 更新答案
    qdrant.update_question(question_id, question_answer=answer)

    return RegenerateResponse(question_answer=answer)