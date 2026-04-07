"""Extract API - 面经提取接口

从文本或图片中提取面经题目。
"""

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
import tempfile
import os
import base64

from app.agents.vision_extractor import get_vision_extractor
from app.pipelines.ingestion import get_ingestion_pipeline
from app.models.schemas import ExtractedInterview, QuestionItem
from app.utils.logger import logger

router = APIRouter(prefix="/extract", tags=["extract"])


# ========== Request/Response Models ==========

class TextExtractRequest(BaseModel):
    """文本提取请求"""
    text: str


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


# ========== API Endpoints ==========

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
    use_ocr: bool = Form(False)
):
    """从图片提取面经

    上传一张或多张图片，返回结构化的面经数据。
    """
    logger.info(f"Extract from {len(images)} images, use_ocr={use_ocr}")

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
        result = extractor.extract(temp_paths, source_type="image", use_ocr=use_ocr)

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