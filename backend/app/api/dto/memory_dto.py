"""Memory DTO - 记忆数据传输对象

定义记忆 API 的响应模型。
DTO 负责数据传输，不包含业务逻辑。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    """记忆响应（MEMORY.md 主文档）"""

    user_id: str = Field(description="用户唯一标识")
    content: str = Field(description="MEMORY.md 内容（Markdown 格式）")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class MemoryReferenceResponse(BaseModel):
    """记忆引用响应（preferences.md / behaviors.md）"""

    reference_name: str = Field(description="引用名称")
    content: str = Field(description="文件内容（Markdown 格式）")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class MemoryDetailResponse(BaseModel):
    """记忆详情响应（包含主文档和所有引用）"""

    memory: MemoryResponse = Field(description="MEMORY.md 主文档")
    references: list[MemoryReferenceResponse] = Field(description="引用文件列表")


# ========== Update Request DTOs ==========


class UpdatePreferencesRequest(BaseModel):
    """更新偏好设置请求"""

    content: str = Field(description="preferences.md 内容（Markdown 格式）")


class UpdateBehaviorsRequest(BaseModel):
    """更新行为模式请求"""

    content: str = Field(description="behaviors.md 内容（Markdown 格式）")


# ========== DTO Converters ==========


def memory_to_response(memory) -> MemoryResponse:
    """将 Memory 聚合转换为响应 DTO

    Args:
        memory: Memory 聚合根（Domain 类型）

    Returns:
        MemoryResponse DTO
    """
    return MemoryResponse(
        user_id=memory.user_id,
        content=memory.content,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


def reference_to_response(reference) -> MemoryReferenceResponse:
    """将 MemoryReference 实体转换为响应 DTO

    Args:
        reference: MemoryReference 实体（Domain 类型）

    Returns:
        MemoryReferenceResponse DTO
    """
    return MemoryReferenceResponse(
        reference_name=reference.reference_name,
        content=reference.content,
        updated_at=reference.updated_at,
    )


__all__ = [
    "MemoryResponse",
    "MemoryReferenceResponse",
    "MemoryDetailResponse",
    "UpdatePreferencesRequest",
    "UpdateBehaviorsRequest",
    "memory_to_response",
    "reference_to_response",
]