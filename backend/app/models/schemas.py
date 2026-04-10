"""核心数据模型定义模块"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import IntentType, MasteryLevel, QuestionType


class QuestionItem(BaseModel):
    """单题数据模型

    Attributes:
        question_id: 题目唯一标识，由 MD5(company + question_text) 生成
        question_text: 题目文本内容
        question_type: 题目类型（knowledge/project/behavioral/scenario）
        requires_async_answer: 是否需要异步生成答案（knowledge/scenario 类型为 True）
        core_entities: 考察的知识点实体列表
        mastery_level: 熟练度等级，默认为 0（未掌握）
        company: 公司名称（从 ExtractedInterview 继承）
        position: 岗位名称（从 ExtractedInterview 继承）
        cluster_ids: 所属考点簇 ID 列表（一道题可能属于多个簇）
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
    cluster_ids: list[str] = Field(
        default_factory=list, description="所属考点簇 ID 列表"
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
    company: str = Field(default="", description="公司名称")
    position: str = Field(default="", description="岗位名称")
    questions: list[QuestionItem] = Field(default_factory=list, description="题目列表")


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
    cluster_ids: list[str] = Field(
        default_factory=list, description="所属考点簇 ID 列表"
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
    core_entities: Optional[List[str]] = Field(
        default=None, description="知识点过滤（匹配任一知识点）"
    )
    cluster_ids: Optional[List[str]] = Field(
        default=None, description="考点簇过滤（匹配任一簇）"
    )


class SearchResult(BaseModel):
    """向量检索结果模型"""

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    mastery_level: int = Field(description="熟练度等级")
    question_type: str = Field(description="题目类型")
    core_entities: list[str] = Field(
        default_factory=list, description="知识点实体列表"
    )
    cluster_ids: list[str] = Field(
        default_factory=list, description="考点簇 ID 列表"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="题目元数据"
    )
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


class RouterResult(BaseModel):
    """路由结果模型

    Router Agent 输出的结构化结果，包含意图分类和参数提取。
    """

    intent: IntentType = Field(description="意图类型: query/ingest/practice/stats")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="提取的参数，包含 company, position, question 等",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="置信度"
    )
    original_text: str = Field(description="原始用户输入")


class ScoreResult(BaseModel):
    """打分结果模型

    Scorer Agent 输出的结构化结果，包含评分和反馈。
    """

    question_id: str = Field(description="题目唯一标识")
    question_text: str = Field(description="题目文本")
    standard_answer: Optional[str] = Field(
        default=None, description="标准答案"
    )
    user_answer: str = Field(description="用户提交的答案")
    score: int = Field(ge=0, le=100, description="评分 0-100")
    mastery_level: MasteryLevel = Field(description="熟练度等级")
    strengths: list[str] = Field(
        default_factory=list, description="答案优点"
    )
    improvements: list[str] = Field(
        default_factory=list, description="改进建议"
    )
    feedback: str = Field(description="综合反馈")


class Cluster(BaseModel):
    """考点簇模型

    将相似题目聚类为一个考点簇，便于组织和管理题目。
    """

    cluster_id: str = Field(description="唯一标识，如 cluster_qlora_memory")
    cluster_name: str = Field(description="考点簇名称，如 QLoRA 显存优化")
    summary: str = Field(description="一句话总结")
    question_ids: list[str] = Field(
        default_factory=list, description="该簇下所有题目 ID"
    )
    knowledge_points: list[str] = Field(
        default_factory=list, description="核心知识点列表"
    )
    frequency: int = Field(default=0, description="该簇题目总数")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)