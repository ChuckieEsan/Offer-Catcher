"""Memory API - 记忆接口

提供用户记忆查询和更新能力。
"""

from fastapi import APIRouter, Header
from typing import Optional

from app.application.services.memory_service import get_memory_service
from app.api.dto.memory_dto import (
    MemoryResponse,
    MemoryReferenceResponse,
    MemoryDetailResponse,
    UpdatePreferencesRequest,
    UpdateBehaviorsRequest,
    memory_to_response,
    reference_to_response,
)
from app.infrastructure.common.logger import logger


router = APIRouter(prefix="/memory", tags=["memory"])


def get_user_id(x_user_id: Optional[str] = None) -> str:
    """获取用户 ID"""
    return x_user_id or "default_user"


@router.get("/{user_id}", response_model=MemoryDetailResponse)
async def get_memory(user_id: str):
    """获取用户完整记忆（MEMORY.md + references）

    Args:
        user_id: 用户唯一标识

    Returns:
        MemoryDetailResponse 包含主文档和引用列表
    """
    logger.info(f"Get memory for user: {user_id}")
    service = get_memory_service()
    memory = service.get_memory(user_id)

    return MemoryDetailResponse(
        memory=memory_to_response(memory),
        references=[reference_to_response(ref) for ref in memory.references],
    )


@router.put("/{user_id}/preferences")
async def update_preferences(
    user_id: str,
    request: UpdatePreferencesRequest,
    x_user_id: Optional[str] = Header(None),
):
    """更新用户偏好设置

    Args:
        user_id: 用户唯一标识
        request: 更新请求（包含 content）
        x_user_id: Header 中的用户 ID（可选）

    Returns:
        操作结果
    """
    # 使用 URL 中的 user_id 或 Header 中的 user_id
    effective_user_id = user_id if user_id != "default_user" else get_user_id(x_user_id)
    logger.info(f"Update preferences for user: {effective_user_id}")

    service = get_memory_service()
    service.update_preferences(effective_user_id, request.content)

    return {"success": True, "message": "偏好设置已更新"}


@router.put("/{user_id}/behaviors")
async def update_behaviors(
    user_id: str,
    request: UpdateBehaviorsRequest,
    x_user_id: Optional[str] = Header(None),
):
    """更新用户行为模式

    Args:
        user_id: 用户唯一标识
        request: 更新请求（包含 content）
        x_user_id: Header 中的用户 ID（可选）

    Returns:
        操作结果
    """
    # 使用 URL 中的 user_id 或 Header 中的 user_id
    effective_user_id = user_id if user_id != "default_user" else get_user_id(x_user_id)
    logger.info(f"Update behaviors for user: {effective_user_id}")

    service = get_memory_service()
    service.update_behaviors(effective_user_id, request.content)

    return {"success": True, "message": "行为模式已更新"}


@router.get("/{user_id}/preferences", response_model=MemoryReferenceResponse)
async def get_preferences(user_id: str):
    """获取用户偏好设置

    Args:
        user_id: 用户唯一标识

    Returns:
        preferences.md 内容
    """
    logger.info(f"Get preferences for user: {user_id}")
    service = get_memory_service()
    content = service.get_preferences(user_id)

    return MemoryReferenceResponse(
        reference_name="preferences",
        content=content,
    )


@router.get("/{user_id}/behaviors", response_model=MemoryReferenceResponse)
async def get_behaviors(user_id: str):
    """获取用户行为模式

    Args:
        user_id: 用户唯一标识

    Returns:
        behaviors.md 内容
    """
    logger.info(f"Get behaviors for user: {user_id}")
    service = get_memory_service()
    content = service.get_behaviors(user_id)

    return MemoryReferenceResponse(
        reference_name="behaviors",
        content=content,
    )


@router.get("/{user_id}/content", response_model=MemoryResponse)
async def get_memory_content(user_id: str):
    """获取 MEMORY.md 主文档

    Args:
        user_id: 用户唯一标识

    Returns:
        MEMORY.md 内容
    """
    logger.info(f"Get MEMORY.md for user: {user_id}")
    service = get_memory_service()
    content = service.get_memory_content(user_id)

    return MemoryResponse(
        user_id=user_id,
        content=content,
    )


__all__ = ["router"]