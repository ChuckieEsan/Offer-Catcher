"""Questions API - 题目管理接口

提供题目的 CRUD 操作。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from app.db.qdrant_client import get_qdrant_manager
from app.agents.answer_specialist import get_answer_specialist
from app.models.schemas import QdrantQuestionPayload, SearchResult, QuestionItem, SearchFilter
from app.models.enums import QuestionType, MasteryLevel
from app.utils.logger import logger

router = APIRouter(prefix="/questions", tags=["questions"])


# ========== Helper Functions ==========

def payload_to_question_item(payload: QdrantQuestionPayload) -> QuestionItem:
    """将 QdrantQuestionPayload 转换为 QuestionItem

    存储模型 → 业务模型
    """
    return QuestionItem(
        question_id=payload.question_id,
        question_text=payload.question_text,
        company=payload.company,
        position=payload.position,
        question_type=QuestionType(payload.question_type),
        core_entities=payload.core_entities,
        mastery_level=MasteryLevel(payload.mastery_level),
        metadata=payload.metadata,
        cluster_ids=payload.cluster_ids,
    )


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
    cluster_id: Optional[str] = Query(None, description="聚类过滤"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取题目列表

    支持按公司、岗位、类型、熟练度、聚类过滤，以及关键词搜索。
    使用 Qdrant 服务端过滤，避免内存溢出。
    """
    logger.info(f"List questions: company={company}, cluster_id={cluster_id}, keyword={keyword}, page={page}")

    qdrant = get_qdrant_manager()

    # 构建服务端过滤条件
    filter_conditions = SearchFilter(
        company=company,
        position=position,
        question_type=question_type,
        mastery_level=mastery_level,
        cluster_ids=[cluster_id] if cluster_id else None,
    )

    # 如果有关键词搜索，需要获取更多数据再内存过滤
    if keyword:
        # 获取所有符合条件的数据（服务端过滤后）
        all_filtered = qdrant.scroll_with_filter(filter_conditions, limit=10000)

        # 关键词内存过滤
        keyword_lower = keyword.lower()
        filtered = [q for q in all_filtered if keyword_lower in q.question_text.lower()]

        total = len(filtered)

        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        items = filtered[start:end]
    else:
        # 无关键词，使用服务端计数
        total = qdrant.count_with_filter(filter_conditions)

        # 计算分页范围
        start = (page - 1) * page_size
        end = start + page_size

        # 服务端过滤 + 分页：获取略多于当前页的数据
        # Qdrant scroll 不支持 offset，需要从开始遍历到 end
        items = qdrant.scroll_with_filter(filter_conditions, limit=end)
        items = items[start:end]

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
async def regenerate_answer(question_id: str, preview: bool = Query(True, description="是否仅预览（不保存）")):
    """重新生成答案

    TODO: 改用 SSE 流式返回，避免长时间等待
          - 后端: 改为 StreamingResponse，流式返回生成过程
          - 前端: 使用 EventSource 接收流式数据，实时显示生成进度

    Args:
        question_id: 题目 ID
        preview: 是否仅预览。默认 True，只返回新答案不保存。
                 设为 False 时会直接保存到数据库。

    Returns:
        生成的新答案
    """
    logger.info(f"Regenerate answer: {question_id}, preview={preview}")

    qdrant = get_qdrant_manager()
    question_payload = qdrant.get_question(question_id)

    if not question_payload:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 存储模型 → 业务模型
    question_item = payload_to_question_item(question_payload)

    # 在线程池中运行同步的 LLM 调用，避免阻塞事件循环
    specialist = get_answer_specialist()
    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(None, specialist.generate_answer, question_item)

    # 仅当 preview=False 时才保存
    if not preview:
        qdrant.update_question(question_id, question_answer=answer)
        logger.info(f"Answer saved for question: {question_id}")

    return RegenerateResponse(question_answer=answer)