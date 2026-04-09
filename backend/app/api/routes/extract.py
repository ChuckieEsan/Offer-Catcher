"""Extract API - 面经提取接口

从文本或图片中提取面经题目。
支持同步模式和异步任务模式。
"""

from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Header
from pydantic import BaseModel, Field
from typing import List, Optional
import tempfile
import os

from app.agents.vision_extractor import get_vision_extractor
from app.pipelines.ingestion import get_ingestion_pipeline
from app.models.schemas import (
    ExtractedInterview,
    QuestionItem,
    ExtractTask,
    ExtractTaskCreate,
    ExtractTaskUpdate,
    ExtractTaskListItem,
    ExtractTaskStatus,
)
from app.db.postgres_client import get_postgres_client
from app.mq.producer import get_producer
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger

router = APIRouter(prefix="/extract", tags=["extract"])


# ========== Request/Response Models ==========

class TextExtractRequest(BaseModel):
    """文本提取请求"""
    text: str


class ImageExtractRequest(BaseModel):
    """图片提取请求（支持 Base64 和 URL）"""
    images: List[str] = Field(
        ...,
        description="图片源列表，支持 Base64 编码（data:image/xxx;base64,...）或 URL"
    )


class ExtractResponse(BaseModel):
    """提取响应"""
    company: str
    position: str
    questions: List[QuestionItem]


class ConfirmRequest(BaseModel):
    """确认入库请求"""
    interview: ExtractedInterview
    confirmed: bool = True


class ConfirmResponse(BaseModel):
    """确认入库响应"""
    processed: int
    async_tasks: int
    question_ids: List[str] = []


class TaskListResponse(BaseModel):
    """任务列表响应"""
    items: List[ExtractTaskListItem]
    total: int
    page: int
    page_size: int


class TaskSubmitResponse(BaseModel):
    """任务提交响应"""
    task_id: str
    message: str


# ========== Helper Functions ==========

def get_user_id(x_user_id: Optional[str] = None) -> str:
    """获取用户 ID"""
    return x_user_id or "default_user"


# ========== 异步任务 API ==========

@router.post("/submit", response_model=TaskSubmitResponse)
async def submit_extract_task(
    request: ExtractTaskCreate,
    x_user_id: Optional[str] = Header(None),
):
    """提交面经解析任务（异步）

    上传文本或图片，创建解析任务并立即返回 task_id。
    后台 Worker 会异步处理任务。

    Args:
        request: 包含 source_type 和 source_content/source_images
        x_user_id: 用户 ID（Header）

    Returns:
        TaskSubmitResponse 包含 task_id
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Submit extract task: user={user_id}, type={request.source_type}")

    # 创建任务
    pg = get_postgres_client()
    task = pg.create_extract_task(user_id, request)

    # 发送消息到 MQ（通知 Worker 处理）
    try:
        producer = await get_producer()
        mq_msg = MQTaskMessage(
            question_id=task.task_id,  # 复用 MQTaskMessage，用 task_id 作为 question_id
            question_text=f"extract_task:{task.task_id}",
            company="",
            position="",
        )
        await producer.publish_task(mq_msg)
        logger.info(f"Task sent to MQ: {task.task_id}")
    except Exception as e:
        logger.warning(f"Failed to send task to MQ: {e}, task will be polled by worker")

    return TaskSubmitResponse(
        task_id=task.task_id,
        message="任务已提交，请稍后查询结果"
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_extract_tasks(
    status: Optional[str] = Query(None, description="状态过滤: pending/processing/completed/failed/confirmed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    x_user_id: Optional[str] = Header(None),
):
    """获取任务列表

    分页获取当前用户的所有面经解析任务。
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"List extract tasks: user={user_id}, status={status}")

    pg = get_postgres_client()

    # 验证状态值
    valid_statuses = [None, ExtractTaskStatus.PENDING, ExtractTaskStatus.PROCESSING,
                      ExtractTaskStatus.COMPLETED, ExtractTaskStatus.FAILED, ExtractTaskStatus.CONFIRMED]
    if status and status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    offset = (page - 1) * page_size
    items = pg.get_extract_tasks(user_id, status, page_size, offset)
    total = pg.count_extract_tasks(user_id, status)

    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}", response_model=ExtractTask)
async def get_extract_task(
    task_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """获取任务详情

    获取指定任务的完整信息，包括解析结果。
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Get extract task: task_id={task_id}, user={user_id}")

    pg = get_postgres_client()
    task = pg.get_extract_task(task_id, user_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return task


@router.put("/tasks/{task_id}", response_model=ExtractTask)
async def update_extract_task(
    task_id: str,
    request: ExtractTaskUpdate,
    x_user_id: Optional[str] = Header(None),
):
    """编辑任务解析结果

    修改公司、岗位或题目列表。
    仅允许编辑 status=completed 的任务。
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Update extract task: task_id={task_id}")

    pg = get_postgres_client()
    task = pg.get_extract_task(task_id, user_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != ExtractTaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="仅可编辑已完成的任务")

    updated_task = pg.update_extract_task_edit(
        task_id=task_id,
        user_id=user_id,
        company=request.company,
        position=request.position,
        questions=request.questions,
    )

    return updated_task


@router.post("/tasks/{task_id}/confirm", response_model=ConfirmResponse)
async def confirm_extract_task(
    task_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """确认入库

    确认任务解析结果并入库到 Qdrant。
    """
    user_id = get_user_id(x_user_id)
    logger.info(f"Confirm extract task: task_id={task_id}")

    pg = get_postgres_client()
    task = pg.get_extract_task(task_id, user_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != ExtractTaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="仅可确认已完成的任务")

    if not task.result:
        raise HTTPException(status_code=400, detail="任务无解析结果")

    # 入库
    pipeline = get_ingestion_pipeline()
    result = await pipeline.process(task.result)

    # 更新任务状态
    pg.update_extract_task_status(task_id, ExtractTaskStatus.CONFIRMED)

    return ConfirmResponse(
        processed=result.processed,
        async_tasks=result.async_tasks,
        question_ids=result.question_ids
    )


@router.delete("/tasks/{task_id}")
async def delete_extract_task(
    task_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """删除任务"""
    user_id = get_user_id(x_user_id)
    logger.info(f"Delete extract task: task_id={task_id}")

    pg = get_postgres_client()
    deleted = pg.delete_extract_task(task_id, user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {"success": True}


# ========== 同步模式 API（保留兼容） ==========

@router.post("/text", response_model=ExtractResponse)
async def extract_text(request: TextExtractRequest):
    """从文本提取面经

    输入文本内容，返回结构化的面经数据。
    """
    logger.info(f"Extract from text: {request.text[:50]}...")

    extractor = get_vision_extractor()
    result = extractor.extract(request.text, source_type="text")

    return ExtractResponse(
        company=result.company,
        position=result.position,
        questions=result.questions
    )


@router.post("/image", response_model=ExtractResponse)
async def extract_image(
    images: List[UploadFile] = File(...),
):
    """从上传的图片文件提取面经

    上传一张或多张图片文件，OCR 识别后返回结构化的面经数据。
    """
    logger.info(f"Extract from {len(images)} uploaded files")

    # 保存上传的图片到临时文件
    temp_paths = []
    for uploaded_file in images:
        suffix = f".{uploaded_file.filename.split('.')[-1]}" if '.' in uploaded_file.filename else ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await uploaded_file.read()
            tmp.write(content)
            temp_paths.append(tmp.name)

    try:
        extractor = get_vision_extractor()
        result = extractor.extract(temp_paths, source_type="image", use_ocr=True)

        return ExtractResponse(
            company=result.company,
            position=result.position,
            questions=result.questions
        )
    finally:
        # 清理临时文件
        for path in temp_paths:
            if os.path.exists(path):
                os.unlink(path)


@router.post("/image/base64", response_model=ExtractResponse)
async def extract_image_base64(request: ImageExtractRequest):
    """从 Base64 或 URL 图片提取面经

    接收 Base64 编码的图片或图片 URL，OCR 识别后返回结构化的面经数据。

    Args:
        request: 包含图片源列表的请求，每个元素可以是：
            - Base64 编码：data:image/jpeg;base64,/9j/4AAQ...
            - URL：https://example.com/image.jpg

    Returns:
        ExtractResponse 结构化的面经数据
    """
    logger.info(f"Extract from {len(request.images)} Base64/URL images")

    extractor = get_vision_extractor()
    result = extractor.extract(request.images, source_type="image", use_ocr=True)

    return ExtractResponse(
        company=result.company,
        position=result.position,
        questions=result.questions
    )


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_ingest(request: ConfirmRequest):
    """确认入库

    确认提取的面经数据并入库。
    """
    logger.info(f"Confirm ingest: company={request.interview.company}, questions={len(request.interview.questions)}")

    if not request.confirmed:
        return ConfirmResponse(processed=0, async_tasks=0, question_ids=[])

    pipeline = get_ingestion_pipeline()
    result = await pipeline.process(request.interview)

    return ConfirmResponse(
        processed=result.processed,
        async_tasks=result.async_tasks,
        question_ids=result.question_ids
    )