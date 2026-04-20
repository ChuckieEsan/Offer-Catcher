"""Memory Domain Module

记忆领域模块，定义用户记忆的核心概念。

核心概念：
- 记忆 = 用户自定义 Skill
- MEMORY.md 主文档（始终加载）
- references 引用文件（按需加载）
- SessionSummary 会话摘要（语义检索）
"""

from app.domain.memory.aggregates import (
    Memory,
    MemoryReference,
    MemoryStatus,
    SessionSummary,
)
from app.domain.memory.events import (
    BehaviorsUpdated,
    MemoryInitialized,
    MemoryUpdated,
    PreferencesUpdated,
    SessionSummaryCreated,
    SkillCreated,
    SkillDeleted,
)
from app.domain.memory.repositories import (
    MemoryRepository,
    SessionSummaryRepository,
)
from app.domain.memory.templates import (
    MEMORY_MD_TEMPLATE,
    PREFERENCES_TEMPLATE,
    BEHAVIORS_TEMPLATE,
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)

__all__ = [
    # Aggregates
    "Memory",
    "MemoryReference",
    "MemoryStatus",
    "SessionSummary",
    # Events
    "MemoryInitialized",
    "MemoryUpdated",
    "PreferencesUpdated",
    "BehaviorsUpdated",
    "SessionSummaryCreated",
    "SkillCreated",
    "SkillDeleted",
    # Repositories
    "MemoryRepository",
    "SessionSummaryRepository",
    # Templates
    "MEMORY_MD_TEMPLATE",
    "PREFERENCES_TEMPLATE",
    "BEHAVIORS_TEMPLATE",
    "get_memory_template",
    "get_preferences_template",
    "get_behaviors_template",
]