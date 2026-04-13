"""记忆管理模块

提供用户长期记忆的存储和管理功能。

核心概念：记忆 = 用户自定义 Skill

命名空间结构：
    ("memory", user_id) → MEMORY.md
    ("memory", user_id, "references", "preferences") → preferences.md
    ("memory", user_id, "references", "behaviors") → behaviors.md
    ("memory", user_id, "references", "skills", skill_name, "SKILL.md") → SKILL.md

使用方式：
    - MEMORY.md 始终加载，提供概要信息
    - references 按需查询，使用 load_memory_reference Tool
"""

# 存储管理
from app.memory.store import MemoryStore, get_memory_store

# 读写接口
from app.memory.io import (
    read_memory,
    write_memory,
    read_memory_reference,
    write_memory_reference,
    delete_memory_reference,
    list_memory_references,
    memory_exists,
)

# 模板
from app.memory.templates import (
    MEMORY_TEMPLATE,
    PREFERENCES_TEMPLATE,
    BEHAVIORS_TEMPLATE,
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)

# 初始化
from app.memory.init import (
    initialize_user_memory,
    ensure_user_memory,
)

__all__ = [
    # 存储
    "MemoryStore",
    "get_memory_store",
    # 读写
    "read_memory",
    "write_memory",
    "read_memory_reference",
    "write_memory_reference",
    "delete_memory_reference",
    "list_memory_references",
    "memory_exists",
    # 模板
    "MEMORY_TEMPLATE",
    "PREFERENCES_TEMPLATE",
    "BEHAVIORS_TEMPLATE",
    "get_memory_template",
    "get_preferences_template",
    "get_behaviors_template",
    # 初始化
    "initialize_user_memory",
    "ensure_user_memory",
]