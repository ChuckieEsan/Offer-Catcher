"""ExtractTask DTO 转换器和请求/响应模型

将 ExtractTask domain 聚合转换为 API 响应格式。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ========== Request Models ==========


class ExtractTaskCreate(BaseModel):
    """创建解析任务请求"""

    source_type: str = Field(description="来源类型: image / text")
    source_content: Optional[str] = Field(default=None, description="文本内容")
    source_images: Optional[List[str]] = Field(default=None, description="图片 Base64 列表")


class ExtractTaskUpdate(BaseModel):
    """更新解析结果请求"""

    company: Optional[str] = None
    position: Optional[str] = None
    questions: Optional[List[dict]] = None


# ========== Response Models ==========


class ExtractTaskListItem(BaseModel):
    """任务列表项（精简版）"""

    task_id: str
    status: str
    source_type: str
    company: str = ""
    position: str = ""
    question_count: int = 0
    created_at: datetime
    updated_at: datetime


# ========== DTO 转换函数 ==========


def extract_task_to_response(task) -> dict:
    """将 ExtractTask 聚合转换为 API 响应字典

    Args:
        task: ExtractTask domain 聚合

    Returns:
        API 响应字典
    """
    response = {
        "task_id": task.task_id,
        "user_id": task.user_id,
        "source_type": task.source_type,
        "source_content": task.source_content,
        "source_images": task.source_images,
        "status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }

    # 添加提取结果
    if task.extracted_interview:
        response["result"] = task.extracted_interview

    return response


def extract_tasks_to_list_items(
    tasks: List,
) -> List[ExtractTaskListItem]:
    """将 ExtractTask 列表转换为 ExtractTaskListItem 列表

    Args:
        tasks: ExtractTask domain 聚合列表

    Returns:
        ExtractTaskListItem 模型列表
    """
    items = []
    for task in tasks:
        company = ""
        position = ""
        question_count = 0

        if task.extracted_interview:
            company = task.extracted_interview.get("company", "")
            position = task.extracted_interview.get("position", "")
            question_count = len(task.extracted_interview.get("questions", []))

        items.append(
            ExtractTaskListItem(
                task_id=task.task_id,
                status=task.status,
                source_type=task.source_type,
                company=company,
                position=position,
                question_count=question_count,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
        )

    return items


__all__ = [
    "ExtractTaskCreate",
    "ExtractTaskUpdate",
    "ExtractTaskListItem",
    "extract_task_to_response",
    "extract_tasks_to_list_items",
]