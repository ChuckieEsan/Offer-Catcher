"""ExtractTask DTO 转换器

将 ExtractTask domain 聚合转换为 API 响应格式。
"""

from __future__ import annotations

from typing import List

from app.domain.question.aggregates import ExtractTask
from app.models import ExtractTaskListItem


def extract_task_to_response(task: ExtractTask) -> dict:
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
    tasks: List[ExtractTask],
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
    "extract_task_to_response",
    "extract_tasks_to_list_items",
]