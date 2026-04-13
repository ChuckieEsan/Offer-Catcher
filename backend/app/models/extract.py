"""面经解析任务相关数据模型

用于异步解析面经图片/文本的任务管理。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.question import QuestionItem, ExtractedInterview


class ExtractTaskStatus:
    """面经解析任务状态枚举"""
    PENDING = "pending"         # 待处理
    PROCESSING = "processing"   # 处理中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    CONFIRMED = "confirmed"     # 已确认入库


class ExtractTask(BaseModel):
    """面经解析任务模型

    用于异步解析面经图片/文本，支持用户查看和编辑解析结果。
    """

    task_id: str = Field(description="任务 ID (UUID)")
    user_id: str = Field(description="用户 ID")

    # 输入
    source_type: str = Field(description="来源类型: image / text")
    source_content: Optional[str] = Field(default=None, description="文本内容（text 类型）")
    source_images_gz: Optional[List[str]] = Field(
        default=None,
        description="图片 Base64 列表（image 类型）"
    )

    # 状态
    status: str = Field(default=ExtractTaskStatus.PENDING, description="任务状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    # 解析结果（可编辑）
    result: Optional[ExtractedInterview] = Field(default=None, description="解析结果")


class ExtractTaskCreate(BaseModel):
    """创建解析任务请求"""

    source_type: str = Field(description="来源类型: image / text")
    source_content: Optional[str] = Field(default=None, description="文本内容")
    source_images: Optional[List[str]] = Field(default=None, description="图片 Base64 列表")


class ExtractTaskUpdate(BaseModel):
    """更新解析结果请求"""

    company: Optional[str] = None
    position: Optional[str] = None
    questions: Optional[List[QuestionItem]] = None


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


__all__ = [
    "ExtractTaskStatus",
    "ExtractTask",
    "ExtractTaskCreate",
    "ExtractTaskUpdate",
    "ExtractTaskListItem",
]