"""题库领域

题库领域是核心领域，包含：
- Question 聚合：题目聚合根
- Cluster 聚合：考点簇聚合根
- ExtractTask 聚合：面经提取任务聚合根
- Repository Protocol：仓库接口定义
- Domain Events：领域事件

该领域被模拟面试和智能对话领域依赖。
"""

from app.domain.question.aggregates import (
    Cluster,
    ExtractTask,
    ExtractTaskStatus,
    Question,
)
from app.domain.question.repositories import (
    ClusterRepository,
    ExtractTaskRepository,
    QuestionRepository,
)
from app.domain.question.events import (
    AnswerGenerated,
    ClusterAssigned,
    ClusterCreated,
    ExtractConfirmed,
    MasteryLevelUpdated,
    QuestionCreated,
    QuestionDeleted,
)
from app.domain.question.utils import (
    generate_question_id,
    generate_short_id,
    verify_question_id,
)

__all__ = [
    # 聚合
    "Question",
    "Cluster",
    "ExtractTask",
    "ExtractTaskStatus",
    # Repository Protocol
    "QuestionRepository",
    "ClusterRepository",
    "ExtractTaskRepository",
    # 领域事件
    "ExtractConfirmed",
    "QuestionCreated",
    "QuestionDeleted",
    "AnswerGenerated",
    "ClusterCreated",
    "ClusterAssigned",
    "MasteryLevelUpdated",
    # 工具函数
    "generate_question_id",
    "generate_short_id",
    "verify_question_id",
]