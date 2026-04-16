"""题库领域事件定义

领域事件用于跨聚合通信和最终一致性。
事件触发后由应用层的事件处理器消费。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExtractConfirmed:
    """提取确认事件

    触发时机：用户确认提取结果入库
    消费者：IngestionService → 创建 Question
    """

    task_id: str
    company: str
    position: str
    question_texts: list[str]
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "ExtractConfirmed",
            "task_id": self.task_id,
            "company": self.company,
            "position": self.position,
            "question_texts": self.question_texts,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class QuestionCreated:
    """题目创建事件

    触发时机：Question 入库成功
    消费者：AnswerWorker → 异步生成答案（仅 knowledge/scenario/algorithm 类型）
    """

    question_id: str
    question_type: str
    question_text: str
    company: str
    position: str
    core_entities: list[str] = field(default_factory=list)
    requires_answer: bool = False
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "QuestionCreated",
            "question_id": self.question_id,
            "question_type": self.question_type,
            "question_text": self.question_text,
            "company": self.company,
            "position": self.position,
            "core_entities": self.core_entities,
            "requires_answer": self.requires_answer,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class QuestionDeleted:
    """题目删除事件

    触发时机：Question 被删除
    消费者：ClusterEventHandler → 更新 Cluster.question_ids
    """

    question_id: str
    cluster_ids: list[str] = field(default_factory=list)
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "QuestionDeleted",
            "question_id": self.question_id,
            "cluster_ids": self.cluster_ids,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class AnswerGenerated:
    """答案生成完成事件

    触发时机：答案生成完成
    消费者：QuestionEventHandler → 更新 Question.answer
    """

    question_id: str
    answer: str
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "AnswerGenerated",
            "question_id": self.question_id,
            "answer": self.answer,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class ClusterCreated:
    """考点簇创建事件

    触发时机：聚类算法创建新簇
    消费者：可选，用于通知或日志
    """

    cluster_id: str
    cluster_name: str
    question_ids: list[str] = field(default_factory=list)
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "ClusterCreated",
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "question_ids": self.question_ids,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class ClusterAssigned:
    """聚类分配事件

    触发时机：聚类完成，题目归属簇
    消费者：QuestionEventHandler → 更新 Question.cluster_ids
    """

    cluster_id: str
    question_ids: list[str] = field(default_factory=list)
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "ClusterAssigned",
            "cluster_id": self.cluster_id,
            "question_ids": self.question_ids,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class MasteryLevelUpdated:
    """熟练度更新事件

    触发时机：用户学习或复习后更新熟练度
    消费者：可选，用于统计或推荐
    """

    question_id: str
    old_level: int
    new_level: int
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "MasteryLevelUpdated",
            "question_id": self.question_id,
            "old_level": self.old_level,
            "new_level": self.new_level,
            "occurred_at": self.occurred_at.isoformat(),
        }


__all__ = [
    "ExtractConfirmed",
    "QuestionCreated",
    "QuestionDeleted",
    "AnswerGenerated",
    "ClusterCreated",
    "ClusterAssigned",
    "MasteryLevelUpdated",
]