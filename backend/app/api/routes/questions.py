"""Questions API - 题目管理接口

提供题目的 CRUD 操作。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio

from app.db.qdrant_client import get_qdrant_manager
from app.agents.answer_specialist import get_answer_specialist
from app.models import QdrantQuestionPayload, QuestionItem, SearchFilter
from app.models.question import QuestionType, MasteryLevel
from app.services.cache_service import get_cache_service
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


def dict_to_payload(data: dict) -> QdrantQuestionPayload:
    """将 dict 转换为 QdrantQuestionPayload

    用于缓存反序列化
    """
    return QdrantQuestionPayload(**data)


def dicts_to_payloads(data_list: List[dict]) -> List[QdrantQuestionPayload]:
    """将 dict 列表转换为 QdrantQuestionPayload 列表

    用于缓存反序列化
    """
    return [QdrantQuestionPayload(**d) for d in data_list]


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


class BatchAnswersRequest(BaseModel):
    """批量获取答案请求"""
    question_ids: List[str] = Field(description="题目 ID 列表")


class BatchAnswersResponse(BaseModel):
    """批量获取答案响应"""
    answers: dict[str, Optional[str]] = Field(description="question_id -> answer 的映射")


# ========== API Endpoints ==========

@router.post("/batch/answers", response_model=BatchAnswersResponse)
async def get_batch_answers(request: BatchAnswersRequest):
    """批量获取题目答案

    根据 question_id 列表批量查询答案，用于导入记录详情页显示答案。

    Args:
        request: 包含 question_ids 列表的请求

    Returns:
        BatchAnswersResponse 包含 question_id -> answer 的映射
    """
    logger.info(f"Get batch answers for {len(request.question_ids)} questions")

    qdrant = get_qdrant_manager()
    answers: dict[str, Optional[str]] = {}

    for question_id in request.question_ids:
        question = qdrant.get_question(question_id)
        if question:
            answers[question_id] = question.question_answer
        else:
            answers[question_id] = None

    return BatchAnswersResponse(answers=answers)


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
    使用 Qdrant 服务端过滤，并通过 Redis 缓存优化查询性能。
    """
    logger.info(f"List questions: company={company}, cluster_id={cluster_id}, keyword={keyword}, page={page}")

    qdrant = get_qdrant_manager()
    cache = get_cache_service()

    # 构建过滤参数（用于缓存哈希）
    filter_params = {
        "company": company,
        "position": position,
        "question_type": question_type,
        "mastery_level": mastery_level,
        "cluster_id": cluster_id,
        "keyword": keyword,
    }

    # 构建服务端过滤条件
    filter_conditions = SearchFilter(
        company=company,
        position=position,
        question_type=question_type,
        mastery_level=mastery_level,
        cluster_ids=[cluster_id] if cluster_id else None,
    )

    # 定义数据获取函数（包含关键词过滤）
    def fetch_all_questions():
        if keyword:
            # 获取所有符合条件的数据（服务端过滤后）
            all_filtered = qdrant.scroll_with_filter(filter_conditions, limit=10000)
            # 关键词内存过滤
            keyword_lower = keyword.lower()
            return [q for q in all_filtered if keyword_lower in q.question_text.lower()]
        else:
            # 无关键词，获取足够多的数据用于分页
            return qdrant.scroll_with_filter(filter_conditions, limit=10000)

    # 通过缓存获取全部过滤后的数据（返回 dict 列表）
    cached_data = cache.get_questions_list(filter_params, fetch_all_questions)

    # 将 dict 转换为 Pydantic 模型
    if cached_data and isinstance(cached_data[0], dict):
        all_items = dicts_to_payloads(cached_data)
    else:
        all_items = cached_data  # 已经是 Pydantic 模型（首次查询）

    # 计算总数和分页
    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_items[start:end]

    return QuestionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{question_id}", response_model=QdrantQuestionPayload)
async def get_question(question_id: str):
    """获取单个题目

    使用缓存防穿透：不存在时缓存空值标记，避免重复穿透到数据库。
    """
    qdrant = get_qdrant_manager()
    cache = get_cache_service()

    def fetch_question():
        return qdrant.get_question(question_id)

    cached_data = cache.get_question_item(question_id, fetch_question)

    if not cached_data:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 将 dict 转换为 Pydantic 模型（如果从缓存读取）
    if isinstance(cached_data, dict):
        question = dict_to_payload(cached_data)
    else:
        question = cached_data  # 已经是 Pydantic 模型

    return question


@router.put("/{question_id}", response_model=QdrantQuestionPayload)
async def update_question(question_id: str, request: QuestionUpdateRequest):
    """更新题目

    如果更新了题目文本，会重新计算 embedding。
    使用延迟双删保证缓存一致性。
    """
    logger.info(f"Update question: {question_id}")

    qdrant = get_qdrant_manager()
    cache = get_cache_service()

    # 检查题目是否存在
    existing = qdrant.get_question(question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 延迟双删：第一次删除缓存
    cache.invalidate_question(question_id)

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

    # 延迟双删：后台任务在 1 秒后再次删除
    asyncio.create_task(cache.invalidate_question_delayed(question_id))

    return qdrant.get_question(question_id)


@router.delete("/{question_id}")
async def delete_question(question_id: str):
    """删除题目

    删除后立即失效缓存。
    """
    logger.info(f"Delete question: {question_id}")

    qdrant = get_qdrant_manager()
    cache = get_cache_service()

    qdrant.delete_question(question_id)

    # 失效缓存
    cache.invalidate_question(question_id)

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
    cache = get_cache_service()
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
        # 失效单个题目缓存
        cache.invalidate_question(question_id)

    return RegenerateResponse(question_answer=answer)