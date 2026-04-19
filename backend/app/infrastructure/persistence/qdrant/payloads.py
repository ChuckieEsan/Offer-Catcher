"""Qdrant 存储 Payload 定义

定义写入 Qdrant 向量数据库时的 Payload 结构和检索结果模型。
作为 Infrastructure 层组件，纯技术实现。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class QdrantQuestionPayload(BaseModel):
    """Qdrant 向量数据库 Payload 定义

    该模型用于定义写入 Qdrant 时的元数据（Payload）结构。
    支持按 company、position、mastery_level、question_type 进行预过滤。
    """

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本内容")
    company: str = Field(description="公司名称（keyword 索引）")
    position: str = Field(description="岗位名称（keyword 索引）")
    mastery_level: int = Field(description="熟练度等级（integer 索引）")
    question_type: str = Field(description="题目类型（keyword 索引）")
    core_entities: list[str] = Field(default_factory=list, description="知识点实体列表")
    question_answer: Optional[str] = Field(default=None, description="生成的标准答案")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间戳")
    metadata: dict[str, Any] = Field(default_factory=dict, description="题目元数据")
    cluster_ids: list[str] = Field(default_factory=list, description="所属考点簇 ID 列表")


class SearchFilter(BaseModel):
    """向量检索过滤器模型

    用于构建 Qdrant 混合检索时的预过滤条件。
    """

    company: Optional[str] = Field(default=None, description="公司名称过滤")
    position: Optional[str] = Field(default=None, description="岗位名称过滤")
    mastery_level: Optional[int] = Field(default=None, description="熟练度等级过滤")
    question_type: Optional[str] = Field(default=None, description="题目类型过滤")
    core_entities: Optional[list[str]] = Field(default=None, description="知识点过滤（匹配任一知识点）")
    cluster_ids: Optional[list[str]] = Field(default=None, description="考点簇过滤（匹配任一簇）")


class SearchResult(BaseModel):
    """向量检索结果模型"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    mastery_level: int = Field(description="熟练度等级")
    question_type: str = Field(description="题目类型")
    core_entities: list[str] = Field(default_factory=list, description="知识点实体列表")
    cluster_ids: list[str] = Field(default_factory=list, description="考点簇 ID 列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="题目元数据")
    question_answer: Optional[str] = Field(default=None, description="生成的标准答案")
    score: float = Field(description="相似度分数")


__all__ = [
    "QdrantQuestionPayload",
    "SearchFilter",
    "SearchResult",
]