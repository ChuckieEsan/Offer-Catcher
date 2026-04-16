"""题目 API DTO

定义题目相关的请求和响应数据传输对象。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ========== 响应模型 ==========


class QuestionResponse(BaseModel):
    """题目响应"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    question_type: str = Field(description="题目类型")
    mastery_level: int = Field(description="熟练度等级")
    core_entities: list[str] = Field(default_factory=list, description="知识点列表")
    answer: Optional[str] = Field(default=None, description="标准答案")
    cluster_ids: list[str] = Field(default_factory=list, description="考点簇列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")

    created_at: Optional[datetime] = Field(default=None, description="创建时间")


class QuestionListResponse(BaseModel):
    """题目列表响应"""

    items: list[QuestionResponse]
    total: int = Field(description="总数")
    page: int = Field(description="页码")
    page_size: int = Field(description="每页数量")


class BatchAnswersResponse(BaseModel):
    """批量答案响应"""

    answers: dict[str, Optional[str]] = Field(description="question_id -> answer 映射")


# ========== 请求模型 ==========


class QuestionCreateRequest(BaseModel):
    """创建题目请求"""

    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    question_type: str = Field(description="题目类型", default="knowledge")
    core_entities: list[str] = Field(default_factory=list, description="知识点列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class QuestionUpdateRequest(BaseModel):
    """更新题目请求"""

    question_text: Optional[str] = Field(default=None, description="新题目文本")
    answer: Optional[str] = Field(default=None, description="新答案")
    mastery_level: Optional[int] = Field(default=None, ge=0, le=2, description="新熟练度")
    core_entities: Optional[list[str]] = Field(default=None, description="新知识点列表")


class BatchAnswersRequest(BaseModel):
    """批量获取答案请求"""

    question_ids: list[str] = Field(description="题目 ID 列表")


__all__ = [
    "QuestionResponse",
    "QuestionListResponse",
    "BatchAnswersResponse",
    "QuestionCreateRequest",
    "QuestionUpdateRequest",
    "BatchAnswersRequest",
]