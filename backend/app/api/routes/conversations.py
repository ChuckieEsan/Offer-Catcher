"""Conversation API - 会话管理接口

提供会话历史的 CRUD 操作。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.db.postgres_client import get_postgres_client
from app.utils.logger import logger

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ========== Request/Response Models ==========

class ConversationResponse(BaseModel):
    """会话响应"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    items: List[ConversationResponse]
    total: int


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """会话详情响应（包含消息）"""
    conversation: ConversationResponse
    messages: List[MessageResponse]


class CreateConversationRequest(BaseModel):
    """创建会话请求"""
    title: str = "新对话"


class UpdateConversationRequest(BaseModel):
    """更新会话请求"""
    title: str


# 默认用户 ID（单用户系统）
DEFAULT_USER_ID = "default_user"


# ========== API Endpoints ==========

@router.get("", response_model=ConversationListResponse)
async def list_conversations(limit: int = Query(50, ge=1, le=100)):
    """获取会话列表（按更新时间倒序）"""
    logger.info(f"List conversations: limit={limit}")

    pg = get_postgres_client()
    conversations = pg.get_conversations(DEFAULT_USER_ID, limit)

    return ConversationListResponse(
        items=[
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in conversations
        ],
        total=len(conversations),
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(request: CreateConversationRequest = CreateConversationRequest()):
    """创建新会话"""
    logger.info(f"Create conversation: title={request.title}")

    pg = get_postgres_client()
    conv = pg.create_conversation(DEFAULT_USER_ID, request.title)

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str):
    """获取会话详情（包含所有消息）"""
    logger.info(f"Get conversation: {conversation_id}")

    pg = get_postgres_client()
    conv = pg.get_conversation(DEFAULT_USER_ID, conversation_id)

    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = pg.get_messages(DEFAULT_USER_ID, conversation_id)

    return ConversationDetailResponse(
        conversation=ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ),
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    """更新会话标题"""
    logger.info(f"Update conversation: {conversation_id}, title={request.title}")

    pg = get_postgres_client()
    success = pg.update_conversation_title(DEFAULT_USER_ID, conversation_id, request.title)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    conv = pg.get_conversation(DEFAULT_USER_ID, conversation_id)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除会话"""
    logger.info(f"Delete conversation: {conversation_id}")

    pg = get_postgres_client()
    success = pg.delete_conversation(DEFAULT_USER_ID, conversation_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True}