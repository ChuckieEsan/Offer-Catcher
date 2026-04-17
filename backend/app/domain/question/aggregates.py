"""题库领域聚合定义

包含题库领域的三个聚合根：
- Question: 题目聚合根
- Cluster: 考点簇聚合根
- ExtractTask: 面经提取任务聚合根

聚合根是聚合的入口点，外部只能通过聚合根访问聚合内部对象。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.shared.enums import MasteryLevel, QuestionType
from app.domain.question.utils import generate_question_id


# ============ Question 聚合 ============


class Question(BaseModel):
    """题目聚合根

    题目是题库领域的核心实体，包含题目内容、类型、答案、所属考点簇等信息。
    所有字段修改必须通过 Question 的方法进行，保证业务规则一致性。

    聚合内规则：
    - question_id 创建后不可变（MD5 哈希）
    - 答案生成/更新是聚合内部操作
    - cluster_ids 是引用列表，不持有 Cluster 实体

    Attributes:
        question_id: 题目唯一标识，MD5(company|question_text)
        question_text: 题目文本内容
        question_type: 题目类型
        mastery_level: 熟练度等级
        company: 公司名称
        position: 岗位名称
        core_entities: 考察的知识点实体列表
        answer: 标准答案（可能为空，异步生成）
        cluster_ids: 所属考点簇 ID 列表（引用）
        metadata: 题目元数据（面试轮次、来源页码等）
    """

    question_id: str = Field(description="题目唯一标识，MD5哈希")
    question_text: str = Field(description="题目文本内容")
    question_type: QuestionType = Field(description="题目类型")
    mastery_level: MasteryLevel = Field(default=MasteryLevel.LEVEL_0)
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    core_entities: list[str] = Field(default_factory=list)
    answer: Optional[str] = Field(default=None, description="标准答案")
    cluster_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        question_text: str,
        company: str,
        position: str,
        question_type: QuestionType,
        core_entities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Question":
        """创建题目（工厂方法）

        使用领域逻辑生成唯一 ID，保证幂等性。

        Args:
            question_text: 题目文本
            company: 公司名称
            position: 岗位名称
            question_type: 题目类型
            core_entities: 知识点实体列表
            metadata: 元数据

        Returns:
            Question 实例
        """
        question_id = generate_question_id(company, question_text)
        return cls(
            question_id=question_id,
            question_text=question_text,
            company=company,
            position=position,
            question_type=question_type,
            core_entities=core_entities or [],
            metadata=metadata or {},
        )

    def update_answer(self, answer: str) -> None:
        """更新答案

        由 AnswerService 或 Worker 调用，更新题目答案。
        """
        self.answer = answer

    def add_cluster(self, cluster_id: str) -> None:
        """添加考点簇引用

        跨聚合引用，只存储 ID，不持有 Cluster 实体。
        """
        if cluster_id not in self.cluster_ids:
            self.cluster_ids.append(cluster_id)

    def remove_cluster(self, cluster_id: str) -> None:
        """移除考点簇引用"""
        self.cluster_ids = [c for c in self.cluster_ids if c != cluster_id]

    def update_mastery(self, level: MasteryLevel) -> None:
        """更新熟练度等级"""
        self.mastery_level = level

    def requires_async_answer(self) -> bool:
        """判断是否需要异步生成答案

        分类熔断机制：
        - knowledge/scenario/algorithm 类型触发异步答案生成
        - project/behavioral 类型熔断（仅存题目不存答案）
        """
        return self.question_type.requires_async_answer()

    def to_context(self) -> str:
        """生成用于 embedding 的上下文文本

        拼接公司、岗位、类型、考点、题目，用于向量嵌入。
        """
        entities = ",".join(self.core_entities) if self.core_entities else "综合"
        return (
            f"公司：{self.company} | "
            f"岗位：{self.position} | "
            f"类型：{self.question_type.value} | "
            f"考点：{entities} | "
            f"题目：{self.question_text}"
        )

    def to_payload(self) -> dict[str, Any]:
        """转换为存储 payload

        用于持久化到 Qdrant 或其他存储。
        """
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "company": self.company,
            "position": self.position,
            "question_type": self.question_type.value,
            "mastery_level": self.mastery_level.value,
            "core_entities": self.core_entities,
            "answer": self.answer,
            "cluster_ids": self.cluster_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Question":
        """从 payload 恢复聚合

        用于从存储层重建聚合实例。
        """
        return cls(
            question_id=payload["question_id"],
            question_text=payload["question_text"],
            company=payload["company"],
            position=payload["position"],
            question_type=QuestionType(payload["question_type"]),
            mastery_level=MasteryLevel(payload["mastery_level"]),
            core_entities=payload.get("core_entities", []),
            answer=payload.get("answer"),
            cluster_ids=payload.get("cluster_ids", []),
            metadata=payload.get("metadata", {}),
        )


# ============ Cluster 聚合 ============


class Cluster(BaseModel):
    """考点簇聚合根

    将相似题目聚类为一个考点簇，便于组织和管理题目。
    Cluster 和 Question 是两个独立的聚合，通过 ID 互相引用。

    聚合内规则：
    - question_ids 是引用列表，不持有 Question 实体
    - 聚类算法负责创建/更新 Cluster

    Attributes:
        cluster_id: 考点簇唯一标识（如 cluster_qlora_memory）
        cluster_name: 考点簇名称（如 QLoRA 显存优化）
        summary: 一句话总结
        knowledge_points: 核心知识点列表
        question_ids: 该簇下所有题目 ID（引用）
        frequency: 该簇题目总数
        created_at: 创建时间
        updated_at: 更新时间
    """

    cluster_id: str = Field(description="考点簇唯一标识")
    cluster_name: str = Field(description="考点簇名称")
    summary: str = Field(description="一句话总结")
    knowledge_points: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list, description="引用的题目 ID")
    frequency: int = Field(default=0, description="题目总数")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        cluster_id: str,
        cluster_name: str,
        summary: str,
        knowledge_points: list[str] | None = None,
    ) -> "Cluster":
        """创建考点簇（工厂方法）

        Args:
            cluster_id: 考点簇唯一标识
            cluster_name: 考点簇名称
            summary: 一句话总结
            knowledge_points: 核心知识点列表

        Returns:
            Cluster 实例
        """
        return cls(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            summary=summary,
            knowledge_points=knowledge_points or [],
        )

    def add_question(self, question_id: str) -> None:
        """添加题目引用

        跨聚合引用，只存储 ID。
        """
        if question_id not in self.question_ids:
            self.question_ids.append(question_id)
            self.frequency = len(self.question_ids)
            self.updated_at = datetime.now()

    def remove_question(self, question_id: str) -> None:
        """移除题目引用"""
        self.question_ids = [q for q in self.question_ids if q != question_id]
        self.frequency = len(self.question_ids)
        self.updated_at = datetime.now()

    def to_payload(self) -> dict[str, Any]:
        """转换为存储 payload"""
        return {
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "summary": self.summary,
            "knowledge_points": self.knowledge_points,
            "question_ids": self.question_ids,
            "frequency": self.frequency,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Cluster":
        """从 payload 恢复聚合"""
        return cls(
            cluster_id=payload["cluster_id"],
            cluster_name=payload["cluster_name"],
            summary=payload["summary"],
            knowledge_points=payload.get("knowledge_points", []),
            question_ids=payload.get("question_ids", []),
            frequency=payload.get("frequency", 0),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )


# ============ ExtractTask 聚合 ============


class ExtractTaskStatus(str):
    """提取任务状态（值对象）

    状态流转：pending -> processing -> completed -> confirmed/cancelled
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ExtractTask(BaseModel):
    """面经提取任务聚合根

    管理面经提取的完整生命周期，从提交到确认入库。
    用户确认后才触发 Question 入库，完成后可归档。

    聚合内规则：
    - 用户确认后才触发入库
    - 完成后可归档，不影响已入库的 Question

    Attributes:
        task_id: 任务唯一标识
        source_type: 来源类型（image/text）
        source_content: 来源内容（图片 URL 或文本）
        status: 任务状态
        extracted_interview: 提取结果（JSON）
        created_at: 创建时间
        updated_at: 更新时间
    """

    task_id: str = Field(description="任务唯一标识")
    source_type: str = Field(description="来源类型：image/text")
    source_content: str = Field(description="来源内容")
    status: str = Field(default=ExtractTaskStatus.PENDING, description="任务状态")
    extracted_interview: Optional[dict[str, Any]] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def start_processing(self) -> None:
        """开始处理

        状态从 pending -> processing
        """
        if self.status != ExtractTaskStatus.PENDING:
            raise ValueError(f"Cannot start processing from status: {self.status}")
        self.status = ExtractTaskStatus.PROCESSING
        self.updated_at = datetime.now()

    def complete(self, extracted_interview: dict[str, Any]) -> None:
        """处理完成

        状态从 processing -> completed
        """
        if self.status != ExtractTaskStatus.PROCESSING:
            raise ValueError(f"Cannot complete from status: {self.status}")
        self.status = ExtractTaskStatus.COMPLETED
        self.extracted_interview = extracted_interview
        self.updated_at = datetime.now()

    def confirm(self) -> None:
        """用户确认入库

        状态从 completed -> confirmed
        """
        if self.status != ExtractTaskStatus.COMPLETED:
            raise ValueError(f"Cannot confirm from status: {self.status}")
        self.status = ExtractTaskStatus.CONFIRMED
        self.updated_at = datetime.now()

    def cancel(self) -> None:
        """取消任务

        可从 pending 或 processing 状态取消
        """
        if self.status not in (ExtractTaskStatus.PENDING, ExtractTaskStatus.PROCESSING):
            raise ValueError(f"Cannot cancel from status: {self.status}")
        self.status = ExtractTaskStatus.CANCELLED
        self.updated_at = datetime.now()

    def is_ready_for_ingestion(self) -> bool:
        """是否可以入库"""
        return self.status == ExtractTaskStatus.COMPLETED and self.extracted_interview is not None

    def to_payload(self) -> dict[str, Any]:
        """转换为存储 payload"""
        return {
            "task_id": self.task_id,
            "source_type": self.source_type,
            "source_content": self.source_content,
            "status": self.status,
            "extracted_interview": self.extracted_interview,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ExtractTask":
        """从 payload 恢复聚合"""
        return cls(
            task_id=payload["task_id"],
            source_type=payload["source_type"],
            source_content=payload["source_content"],
            status=payload["status"],
            extracted_interview=payload.get("extracted_interview"),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )


__all__ = [
    "Question",
    "Cluster",
    "ExtractTask",
    "ExtractTaskStatus",
]