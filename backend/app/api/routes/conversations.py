"""Conversation API - 会话管理接口

提供会话历史的 CRUD 操作。
支持多用户，通过 user_id 参数区分。
"""

from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.db.postgres_client import get_postgres_client
from app.agents.title_generator import get_title_generator_agent
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


# ========== API Endpoints ==========

def _get_user_id(x_user_id: Optional[str] = None) -> str:
    """从 Header 获取 user_id

    Args:
        x_user_id: X-User-ID Header

    Returns:
        用户 ID，未提供时返回默认值
    """
    return x_user_id or "default_user"


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """获取会话列表（按更新时间倒序）

    Args:
        limit: 返回数量限制
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"List conversations: user={user_id}, limit={limit}")

    pg = get_postgres_client()
    conversations = pg.get_conversations(user_id, limit)

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
async def create_conversation(
    request: CreateConversationRequest = CreateConversationRequest(),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """创建新会话

    Args:
        request: 创建请求
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Create conversation: user={user_id}, title={request.title}")

    pg = get_postgres_client()
    conv = pg.create_conversation(user_id, request.title)

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """获取会话详情（包含所有消息）

    Args:
        conversation_id: 会话 ID
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Get conversation: user={user_id}, conversation={conversation_id}")

    pg = get_postgres_client()
    conv = pg.get_conversation(user_id, conversation_id)

    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = pg.get_messages(user_id, conversation_id)

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
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """更新会话标题

    Args:
        conversation_id: 会话 ID
        request: 更新请求
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Update conversation: user={user_id}, conversation={conversation_id}, title={request.title}")

    pg = get_postgres_client()
    success = pg.update_conversation_title(user_id, conversation_id, request.title)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    conv = pg.get_conversation(user_id, conversation_id)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
):
    """删除会话

    Args:
        conversation_id: 会话 ID
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Delete conversation: user={user_id}, conversation={conversation_id}")

    pg = get_postgres_client()
    success = pg.delete_conversation(user_id, conversation_id)

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

    Args:
        conversation_id: 会话 ID
        x_user_id: 用户 ID（通过 Header 传递）
    """
    user_id = _get_user_id(x_user_id)
    logger.info(f"Generate title: user={user_id}, conversation={conversation_id}")

    pg = get_postgres_client()

    # 获取会话
    conv = pg.get_conversation(user_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 只有标题为"新对话"时才自动生成
    if conv.title != "新对话":
        logger.info(f"Title already customized: {conv.title}, skip generation")
        return ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    # 获取消息
    messages = pg.get_messages(user_id, conversation_id)

    if len(messages) < 6:
        logger.info(f"Messages count {len(messages)} < 6, skip generation")
        return ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    # 生成标题
    agent = get_title_generator_agent()
    new_title = agent.generate_title(messages)

    # 更新标题
    pg.update_conversation_title(user_id, conversation_id, new_title)

    # 获取更新后的会话
    updated_conv = pg.get_conversation(user_id, conversation_id)

    return ConversationResponse(
        id=updated_conv.id,
        title=updated_conv.title,
        created_at=updated_conv.created_at,
        updated_at=updated_conv.updated_at,
    )