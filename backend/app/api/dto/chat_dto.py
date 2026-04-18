"""Chat DTO - 对话数据传输对象

定义对话 API 的请求和响应模型。
DTO 负责数据传输，不包含业务逻辑。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ========== Response Models ==========


class ConversationResponse(BaseModel):
    """对话响应"""

    id: str = Field(description="对话唯一标识")
    title: str = Field(description="对话标题")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class ConversationListResponse(BaseModel):
    """对话列表响应"""

    items: List[ConversationResponse] = Field(description="对话列表")
    total: int = Field(description="总数")


class MessageResponse(BaseModel):
    """消息响应"""

    id: str = Field(description="消息唯一标识")
    role: str = Field(description="角色: user / assistant")
    content: str = Field(description="消息内容")
    created_at: datetime = Field(description="创建时间")


class ConversationDetailResponse(BaseModel):
    """对话详情响应（包含消息）"""

    conversation: ConversationResponse = Field(description="对话信息")
    messages: List[MessageResponse] = Field(description="消息列表")


# ========== Request Models ==========


class CreateConversationRequest(BaseModel):
    """创建对话请求"""

    title: str = Field(default="新对话", description="对话标题")


class UpdateConversationRequest(BaseModel):
    """更新对话请求"""

    title: str = Field(description="新标题")


class AddMessageRequest(BaseModel):
    """追加消息请求"""

    role: str = Field(description="角色: user / assistant")
    content: str = Field(description="消息内容")


# ========== DTO Converters ==========


def conversation_to_response(conv) -> ConversationResponse:
    """将 Conversation 聚合转换为响应 DTO

    Args:
        conv: Conversation 聚合根（Domain 类型）

    Returns:
        ConversationResponse DTO
    """
    return ConversationResponse(
        id=conv.conversation_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def message_to_response(msg) -> MessageResponse:
    """将 Message 实体转换为响应 DTO

    Args:
        msg: Message 实体（Domain 类型）

    Returns:
        MessageResponse DTO
    """
    role = msg.role.value if hasattr(msg.role, "value") else msg.role
    return MessageResponse(
        id=msg.message_id,
        role=role,
        content=msg.content,
        created_at=msg.created_at,
    )


__all__ = [
    # Response
    "ConversationResponse",
    "ConversationListResponse",
    "MessageResponse",
    "ConversationDetailResponse",
    # Request
    "CreateConversationRequest",
    "UpdateConversationRequest",
    "AddMessageRequest",
    # Converters
    "conversation_to_response",
    "message_to_response",
]