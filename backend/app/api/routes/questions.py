"""Questions API - 题目管理接口

提供题目的 CRUD 操作，使用 DDD 架构。
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from app.domain.shared.enums import MasteryLevel, QuestionType
from app.domain.question.aggregates import Question

from app.application.services.question_service import (
    QuestionApplicationService,
    get_question_service,
)

from app.api.dto.question_dto import (
    QuestionCreateRequest,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdateRequest,
    BatchAnswersRequest,
    BatchAnswersResponse,
    RegenerateResponse,
)

from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/questions", tags=["questions"])


# ========== 响应转换 ==========


def question_to_response(question: Question) -> QuestionResponse:
    """将 Question 聚合转换为响应 DTO"""
    return QuestionResponse(
        question_id=question.question_id,
        question_text=question.question_text,
        company=question.company,
        position=question.position,
        question_type=question.question_type.value,
        mastery_level=question.mastery_level.value,
        core_entities=question.core_entities,
        question_answer=question.answer,
        cluster_ids=question.cluster_ids,
        metadata=question.metadata,
    )


# ========== API 端点 ==========


@router.post("/batch/answers", response_model=BatchAnswersResponse)
async def get_batch_answers(request: BatchAnswersRequest):
    """批量获取题目答案

    根据 question_id 列表批量查询答案，用于导入记录详情页显示答案。
    """
    logger.info(f"Get batch answers for {len(request.question_ids)} questions")

    service = get_question_service()
    answers = service.get_batch_answers(request.question_ids)

    return BatchAnswersResponse(answers=answers)


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    company: Optional[str] = Query(None, description="公司过滤"),
    position: Optional[str] = Query(None, description="岗位过滤"),
    question_type: Optional[str] = Query(None, description="题目类型过滤"),
    mastery_level: Optional[int] = Query(None, ge=0, le=2, description="熟练度过滤"),
    cluster_id: Optional[str] = Query(None, description="聚类过滤"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取题目列表

    支持按公司、岗位、类型、熟练度、聚类过滤，以及关键词搜索。
    """
    logger.info(
        f"List questions: company={company}, cluster_id={cluster_id}, "
        f"keyword={keyword}, page={page}"
    )

    service = get_question_service()

    # 转换枚举类型
    qt = QuestionType(question_type) if question_type else None
    ml = MasteryLevel(mastery_level) if mastery_level is not None else None

    # 调用应用服务（暂不使用缓存）
    questions, total = service.list_questions(
        company=company,
        position=position,
        question_type=qt,
        mastery_level=ml,
        cluster_id=cluster_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )

    # 转换响应
    items = [question_to_response(q) for q in questions]

    return QuestionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str):
    """获取单个题目

    使用缓存防穿透：不存在时缓存空值标记，避免重复穿透到数据库。
    """
    service = get_question_service()

    question = service.get_question(question_id)

    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    return question_to_response(question)


@router.post("", response_model=QuestionResponse)
async def create_question(request: QuestionCreateRequest):
    """创建题目"""
    logger.info(f"Create question: company={request.company}, type={request.question_type}")

    service = get_question_service()

    # 转换枚举
    question_type = QuestionType(request.question_type)

    # 调用应用服务
    question = service.create_question(
        question_text=request.question_text,
        company=request.company,
        position=request.position,
        question_type=question_type,
        core_entities=request.core_entities,
        metadata=request.metadata,
    )

    return question_to_response(question)


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(question_id: str, request: QuestionUpdateRequest):
    """更新题目

    如果更新了题目文本，会重新计算 embedding。
    使用延迟双删保证缓存一致性。
    """
    logger.info(f"Update question: {question_id}")

    service = get_question_service()

    # 转换熟练度
    mastery_level = MasteryLevel(request.mastery_level) if request.mastery_level is not None else None

    # 调用应用服务
    question = service.update_question(
        question_id=question_id,
        question_text=request.question_text,
        answer=request.question_answer,
        mastery_level=mastery_level,
        core_entities=request.core_entities,
    )

    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    return question_to_response(question)


@router.delete("/{question_id}")
async def delete_question(question_id: str):
    """删除题目"""
    logger.info(f"Delete question: {question_id}")

    service = get_question_service()

    success = service.delete_question(question_id)

    if not success:
        raise HTTPException(status_code=404, detail="题目不存在")

    return {"success": True}


@router.post("/{question_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_answer(
    question_id: str,
    preview: bool = Query(True, description="是否仅预览（不保存）"),
):
    """重新生成答案

    TODO: 改用 SSE 流式返回，避免长时间等待

    Args:
        question_id: 题目 ID
        preview: 是否仅预览。默认 True，只返回新答案不保存。
                 设为 False 时会直接保存到数据库。

    Returns:
        生成的新答案
    """
    logger.info(f"Regenerate answer: {question_id}, preview={preview}")

    service = get_question_service()

    answer = service.regenerate_answer(question_id, preview=preview)

    if not answer:
        raise HTTPException(status_code=404, detail="题目不存在")

    return RegenerateResponse(question_answer=answer)