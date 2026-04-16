"""领域层共享枚举定义

所有领域共用的枚举类型，遵循 DDD 分层架构原则。
这些枚举是领域逻辑的一部分，不应依赖任何基础设施层。
"""

from enum import Enum


class QuestionType(str, Enum):
    """题目类型枚举

    用于区分不同类型的面试题目，影响答案生成策略和检索逻辑。

    - KNOWLEDGE: 客观基础题（八股文），需要异步生成标准答案
    - PROJECT: 项目深挖题（针对个人简历），无需标准答案
    - BEHAVIORAL: 行为题（软技能），无需标准答案
    - SCENARIO: 场景题（和企业业务场景相关的题目），需要异步生成答案
    - ALGORITHM: 算法题（Leetcode 手撕题目），需要异步生成答案
    """

    KNOWLEDGE = "knowledge"
    PROJECT = "project"
    BEHAVIORAL = "behavioral"
    SCENARIO = "scenario"
    ALGORITHM = "algorithm"

    def requires_async_answer(self) -> bool:
        """判断该题目类型是否需要异步生成答案

        分类熔断机制：
        - knowledge/scenario/algorithm 类型触发异步答案生成
        - project/behavioral 类型熔断（仅存题目不存答案）
        """
        return self in (
            QuestionType.KNOWLEDGE,
            QuestionType.SCENARIO,
            QuestionType.ALGORITHM,
        )


class MasteryLevel(int, Enum):
    """熟练度等级枚举

    用于标识用户对某道题目的掌握程度，支持学习进度追踪。

    - LEVEL_0: 完全不会/未复习
    - LEVEL_1: 比较熟悉
    - LEVEL_2: 已掌握
    """

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2


class DifficultyLevel(str, Enum):
    """难度等级枚举

    用于面试题目难度设置和评分标准调整。

    - EASY: 简单，评分标准宽松
    - MEDIUM: 中等，标准评分
    - HARD: 困难，评分标准严格
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SessionStatus(str, Enum):
    """面试会话状态枚举

    用于管理面试会话的生命周期状态。

    - ACTIVE: 进行中
    - PAUSED: 已暂停
    - COMPLETED: 已完成
    """

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class QuestionStatus(str, Enum):
    """面试题目状态枚举

    用于管理面试过程中单道题目的状态流转。

    - PENDING: 待回答（题目已出，等待用户回答）
    - ANSWERING: 正在回答（用户正在作答）
    - SCORED: 已评分（回答完成并已评分）
    - SKIPPED: 已跳过（用户选择跳过该题）
    """

    PENDING = "pending"
    ANSWERING = "answering"
    SCORED = "scored"
    SKIPPED = "skipped"


class MemoryType(str, Enum):
    """记忆类型枚举

    用于区分长期记忆存储的不同类型。

    - USER_PROFILE: 用户画像（个人信息、技能背景等）
    - SESSION_SUMMARY: 会话摘要（对话或面试的语义摘要）
    - INTERVIEW_INSIGHT: 面试洞察（面试中发现的优劣势、知识盲区）
    """

    USER_PROFILE = "user_profile"
    SESSION_SUMMARY = "session_summary"
    INTERVIEW_INSIGHT = "interview_insight"


class ConversationStatus(str, Enum):
    """对话会话状态枚举

    用于管理对话会话的生命周期状态。

    - ACTIVE: 进行中
    - ARCHIVED: 已归档
    """

    ACTIVE = "active"
    ARCHIVED = "archived"


__all__ = [
    "QuestionType",
    "MasteryLevel",
    "DifficultyLevel",
    "SessionStatus",
    "QuestionStatus",
    "MemoryType",
    "ConversationStatus",
]