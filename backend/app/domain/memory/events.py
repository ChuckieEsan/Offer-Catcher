"""Memory Domain - Domain Events

定义记忆领域的领域事件。
用于跨聚合通信和最终一致性。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MemoryInitialized:
    """记忆初始化事件

    用户首次使用记忆功能时触发。
    """

    user_id: str
    occurred_at: datetime


@dataclass
class MemoryUpdated:
    """记忆更新事件

    MEMORY.md 内容更新时触发。
    """

    user_id: str
    occurred_at: datetime


@dataclass
class PreferencesUpdated:
    """偏好更新事件

    preferences.md 内容更新时触发。
    """

    user_id: str
    occurred_at: datetime


@dataclass
class BehaviorsUpdated:
    """行为模式更新事件

    behaviors.md 内容更新时触发。
    """

    user_id: str
    occurred_at: datetime


@dataclass
class SessionSummaryCreated:
    """会话摘要创建事件

    新的会话摘要写入时触发。
    """

    user_id: str
    conversation_id: str
    summary_id: str
    occurred_at: datetime


@dataclass
class SkillCreated:
    """用户 Skill 创建事件

    用户创建自定义 Skill 时触发。
    """

    user_id: str
    skill_name: str
    occurred_at: datetime


@dataclass
class SkillDeleted:
    """用户 Skill 删除事件

    用户删除自定义 Skill 时触发。
    """

    user_id: str
    skill_name: str
    occurred_at: datetime


__all__ = [
    "MemoryInitialized",
    "MemoryUpdated",
    "PreferencesUpdated",
    "BehaviorsUpdated",
    "SessionSummaryCreated",
    "SkillCreated",
    "SkillDeleted",
]