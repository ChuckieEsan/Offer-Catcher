"""记忆管理模块

提供用户长期记忆的存储和管理功能。

核心概念：记忆 = 用户自定义 Skill

模块结构：
    memory/
    ├── io.py              # 读写接口
    ├── store.py           # PostgresStore 管理
    ├── cursor.py          # 游标管理
    ├── templates.py       # 默认模板
    ├── init.py            # 初始化逻辑
    ├── injection.py       # 记忆注入逻辑
    ├── hooks.py           # Stop Hook（触发 memory agent）
    └── agent/             # Memory Agent 子模块
        ├── agent.py       # Agent 创建和执行
        ├── tools.py       # Agent 专用工具（写入）
        └── prompts/       # Prompt 模板

使用方式：
    # 注入记忆到 Agent 上下文
    from app.memory import inject_memory_context
    inject_memory_context(user_id, messages)

    # 对话结束后触发记忆更新
    from app.memory import trigger_memory_update
    await trigger_memory_update(user_id, conversation_id, messages)
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

# 游标管理
from app.memory.cursor import (
    get_cursor,
    save_cursor,
    delete_cursor,
    get_messages_since_cursor,
    get_last_message_uuid,
    has_memory_writes_since,
)

# 记忆注入
from app.memory.injection import (
    build_memory_context,
    inject_memory_context,
)

# Hooks（触发 memory agent）
from app.memory.hooks import (
    trigger_memory_update,
    trigger_memory_update_sync,
)

# Memory Agent
from app.memory.agent import (
    create_memory_agent,
    run_memory_agent,
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
    # 游标
    "get_cursor",
    "save_cursor",
    "delete_cursor",
    "get_messages_since_cursor",
    "get_last_message_uuid",
    "has_memory_writes_since",
    # 记忆注入
    "build_memory_context",
    "inject_memory_context",
    # Hooks
    "trigger_memory_update",
    "trigger_memory_update_sync",
    # Agent
    "create_memory_agent",
    "run_memory_agent",
]