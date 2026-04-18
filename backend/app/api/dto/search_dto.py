"""Search DTO - 搜索数据传输对象

定义搜索 API 的请求和响应模型。
"""

from typing import List, Optional, Any

from pydantic import BaseModel, Field


# ========== Request Models ==========


class SearchRequest(BaseModel):
    """搜索请求"""

    query: str = Field(description="搜索关键词")
    company: Optional[str] = Field(default=None, description="公司过滤")
    position: Optional[str] = Field(default=None, description="岗位过滤")
    mastery_level: Optional[int] = Field(default=None, ge=0, le=2, description="熟练度过滤")
    question_type: Optional[str] = Field(default=None, description="题目类型过滤")
    core_entities: Optional[List[str]] = Field(default=None, description="知识点过滤")
    cluster_ids: Optional[List[str]] = Field(default=None, description="聚类过滤")
    k: int = Field(default=10, ge=1, le=100, description="返回数量")
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1, description="相似度阈值")


# ========== Response Models ==========


class SearchResultItem(BaseModel):
    """搜索结果项"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    mastery_level: int = Field(description="熟练度等级")
    question_type: str = Field(description="题目类型")
    core_entities: List[str] = Field(default_factory=list, description="知识点列表")
    cluster_ids: List[str] = Field(default_factory=list, description="聚类 ID 列表")
    metadata: dict = Field(default_factory=dict, description="元数据")
    question_answer: Optional[str] = Field(default=None, description="标准答案")


class SearchResponse(BaseModel):
    """搜索响应"""

    results: List[SearchResultItem] = Field(description="搜索结果列表")


# ========== DTO Converters ==========


def to_search_result_item(item) -> SearchResultItem:
    """将搜索结果转换为 DTO

    Args:
        item: 搜索结果（支持 dict 或对象）

    Returns:
        SearchResultItem DTO
    """
    if isinstance(item, dict):
        return SearchResultItem(
            question_id=item.get("question_id"),
            question_text=item.get("question_text"),
            company=item.get("company"),
            position=item.get("position"),
            mastery_level=item.get("mastery_level"),
            question_type=item.get("question_type"),
            core_entities=item.get("core_entities", []),
            cluster_ids=item.get("cluster_ids", []),
            metadata=item.get("metadata", {}),
            question_answer=item.get("question_answer"),
        )
    else:
        # 对象类型
        return SearchResultItem(
            question_id=item.question_id,
            question_text=item.question_text,
            company=item.company,
            position=item.position,
            mastery_level=item.mastery_level,
            question_type=item.question_type,
            core_entities=item.core_entities or [],
            cluster_ids=item.cluster_ids or [],
            metadata=item.metadata or {},
            question_answer=item.question_answer,
        )


__all__ = [
    "SearchRequest",
    "SearchResultItem",
    "SearchResponse",
    "to_search_result_item",
]