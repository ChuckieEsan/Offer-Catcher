"""核心数据模型定义模块"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import MasteryLevel, QuestionType


class QuestionItem(BaseModel):
    """单题数据模型

    Attributes:
        question_id: 题目唯一标识，由 MD5(company + question_text) 生成
        question_text: 题目文本内容
        question_type: 题目类型（knowledge/project/behavioral）
        requires_async_answer: 是否需要异步生成答案（仅 knowledge 类型为 True）
        core_entities: 考察的知识点实体列表
        mastery_level: 熟练度等级，默认为 0（未掌握）
        company: 公司名称（从 ExtractedInterview 继承）
        position: 岗位名称（从 ExtractedInterview 继承）
    """

    question_id: str = Field(description="题目唯一标识，MD5哈希值")
    question_text: str = Field(description="题目文本内容")
    question_type: QuestionType = Field(description="题目类型")
    requires_async_answer: bool = Field(
        default=False, description="是否需要异步生成答案"
    )
    core_entities: list[str] = Field(
        default_factory=list, description="考察的知识点实体列表"
    )
    mastery_level: MasteryLevel = Field(
        default=MasteryLevel.LEVEL_0, description="熟练度等级"
    )
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="题目元数据，如面试轮次、来源页码等"
    )


class ExtractedInterview(BaseModel):
    """面试经验数据总线模型（Vision Extractor 输出）

    Attributes:
        source_type: 数据来源类型，默认为 image
        company: 公司名称（需经过静态词典标准化）
        position: 岗位名称
        questions: 题目列表
    """

    source_type: str = Field(default="image", description="数据来源类型")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    questions: list[QuestionItem] = Field(default_factory=list, description="题目列表")


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
    core_entities: list[str] = Field(
        default_factory=list, description="知识点实体列表"
    )
    question_answer: Optional[str] = Field(
        default=None, description="生成的标准答案"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="创建时间戳"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="题目元数据"
    )


class SearchFilter(BaseModel):
    """向量检索过滤器模型

    用于构建 Qdrant 混合检索时的预过滤条件。
    """

    company: Optional[str] = Field(default=None, description="公司名称过滤")
    position: Optional[str] = Field(default=None, description="岗位名称过滤")
    mastery_level: Optional[int] = Field(default=None, description="熟练度等级过滤")
    question_type: Optional[str] = Field(
        default=None, description="题目类型过滤"
    )


class SearchResult(BaseModel):
    """向量检索结果模型"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    mastery_level: int = Field(description="熟练度等级")
    question_type: str = Field(description="题目类型")
    question_answer: Optional[str] = Field(
        default=None, description="生成的标准答案"
    )
    score: float = Field(description="相似度分数")


class MQTaskMessage(BaseModel):
    """RabbitMQ 任务消息模型

    用于在主系统和异步 Worker 之间传递任务上下文。
    """

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    core_entities: list[str] = Field(
        default_factory=list, description="知识点实体列表"
    )