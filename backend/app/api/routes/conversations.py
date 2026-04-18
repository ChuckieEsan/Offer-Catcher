"""Conversation API - 会话管理接口

提供会话历史的 CRUD 操作。
使用 DDD 架构：Application Service 编排用例，DTO 传输数据。
"""

from fastapi import APIRouter, HTTPException, Query, Header
from typing import Optional

from app.application.services.chat_service import get_chat_service
from app.api.dto.chat_dto import (
    ConversationResponse,
    ConversationListResponse,
    MessageResponse,
    ConversationDetailResponse,
    CreateConversationRequest,
    UpdateConversationRequest,
    conversation_to_response,
    message_to_response,
)
from app.agents.title_generator import get_title_generator_agent
from app.infrastructure.common.logger import logger

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ========== Helper Functions ==========


def _get_user_id(x_user_id: Optional[str] = None) -> str:
    """从 Header 获取 user_id"""
    return x_user_id or "default_user"


# ========== API Endpoints ==========


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """获取会话列表（按更新时间倒序）"""
    user_id = _get_user_id(x_user_id)
    logger.info(f"List conversations: user={user_id}, limit={limit}")

    service = get_chat_service()
    conversations = service.list_conversations(user_id, limit)

    return ConversationListResponse(
        items=[conversation_to_response(c) for c in conversations],
        total=len(conversations),
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest = CreateConversationRequest(),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """创建新会话"""
    user_id = _get_user_id(x_user_id)
    logger.info(f"Create conversation: user={user_id}, title={request.title}")

    service = get_chat_service()
    conversation = service.create_conversation(user_id, request.title)

    return conversation_to_response(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """获取会话详情（包含所有消息）"""
    user_id = _get_user_id(x_user_id)
    logger.info(f"Get conversation: user={user_id}, conversation={conversation_id}")

    service = get_chat_service()
    conversation = service.get_conversation(user_id, conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 直接使用聚合中的 messages
    return ConversationDetailResponse(
        conversation=conversation_to_response(conversation),
        messages=[message_to_response(m) for m in conversation.messages],
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """更新会话标题"""
    user_id = _get_user_id(x_user_id)
    logger.info(f"Update conversation: user={user_id}, conversation={conversation_id}")

    service = get_chat_service()
    success = service.update_title(user_id, conversation_id, request.title)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    conversation = service.get_conversation(user_id, conversation_id)
    return conversation_to_response(conversation)


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """删除会话"""
    user_id = _get_user_id(x_user_id)
    logger.info(f"Delete conversation: user={user_id}, conversation={conversation_id}")

    service = get_chat_service()
    success = service.delete_conversation(user_id, conversation_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True}


@router.post("/{conversation_id}/generate-title", response_model=ConversationResponse)
async def generate_conversation_title(
    conversation_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """自动生成会话标题

    根据对话内容生成简洁的标题，适用于标题为"新对话"的会话。
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Generate title: user={user_id}, conversation={conversation_id}")

    service = get_chat_service()

    # 获取标题生成器 Agent
    title_agent = get_title_generator_agent()

    # 使用 Application Service 生成标题
    new_title = service.generate_title(
        user_id=user_id,
        conversation_id=conversation_id,
        title_generator=lambda messages: title_agent.generate_title(messages),
    )

    # 获取更新后的会话
    conversation = service.get_conversation(user_id, conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    return conversation_to_response(conversation)