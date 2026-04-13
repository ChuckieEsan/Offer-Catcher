"""会话相关数据模型

包含历史对话、消息和会话摘要的数据结构定义。
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    """对话数据模型"""

    id: str = Field(description="对话唯一标识")
    user_id: str = Field(description="用户 ID")
    title: str = Field(description="对话标题")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class Message(BaseModel):
    """消息数据模型"""

    id: str = Field(description="消息唯一标识")
    conversation_id: str = Field(description="所属对话 ID")
    user_id: str = Field(description="用户 ID")
    role: str = Field(description="角色: user / assistant")
    content: str = Field(description="消息内容")
    created_at: datetime = Field(description="创建时间")


class SessionSummary(BaseModel):
    """会话摘要数据模型

    用于长期记忆，存储对话的语义摘要。
    """

    conversation_id: str = Field(description="会话 ID")
    user_id: str = Field(description="用户 ID")
    summary: str = Field(description="会话摘要内容")
    embedding: Optional[List[float]] = Field(default=None, description="语义向量（1024 维）")
    session_type: str = Field(description="会话类型: chat / interview")
    metadata: Optional[dict] = Field(default=None, description="元数据")
    created_at: datetime = Field(description="创建时间")


class SessionSummarySearchResult(BaseModel):
    """会话摘要检索结果"""

    conversation_id: str = Field(description="会话 ID")
    summary: str = Field(description="会话摘要内容")
    session_type: str = Field(description="会话类型")
    metadata: Optional[dict] = Field(default=None, description="元数据")
    similarity: float = Field(description="语义相似度，范围 [0, 1]")


class SessionSummaryRecentResult(BaseModel):
    """最近会话摘要结果"""

    conversation_id: str = Field(description="会话 ID")
    summary: str = Field(description="会话摘要内容")
    session_type: str = Field(description="会话类型")
    metadata: Optional[dict] = Field(default=None, description="元数据")
    title: str = Field(description="对话标题")
    created_at: datetime = Field(description="创建时间")


__all__ = [
    "Conversation",
    "Message",
    "SessionSummary",
    "SessionSummarySearchResult",
    "SessionSummaryRecentResult",
]