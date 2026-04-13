"""记忆初始化流程

实现用户记忆的初始化逻辑。

触发时机：
- 用户注册时（自动）
- 首次对话时检测到记忆不存在（兜底）
"""

from app.memory.io import (
    memory_exists,
    write_memory,
    write_memory_reference,
)
from app.memory.templates import (
    get_memory_template,
    get_preferences_template,
    get_behaviors_template,
)
from app.utils.logger import logger


def initialize_user_memory(user_id: str) -> bool:
    """初始化用户记忆

    创建 MEMORY.md + preferences.md + behaviors.md。

    Args:
        user_id: 用户 ID

    Returns:
        是否成功初始化（已存在时返回 False）
    """
    # 检查是否已存在
    if memory_exists(user_id):
        logger.debug(f"Memory already exists for user {user_id}")
        return False

    try:
        # 创建 MEMORY.md
        memory_content = get_memory_template(user_id)
        write_memory(user_id, memory_content)

        # 创建 preferences.md
        preferences_content = get_preferences_template()
        write_memory_reference(user_id, "preferences", preferences_content)

        # 创建 behaviors.md
        behaviors_content = get_behaviors_template()
        write_memory_reference(user_id, "behaviors", behaviors_content)

        logger.info(f"Initialized memory for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize memory for user {user_id}: {e}")
        return False


def ensure_user_memory(user_id: str) -> bool:
    """确保用户记忆存在（兜底检查）

    如果不存在，则初始化。

    Args:
        user_id: 用户 ID

    Returns:
        记忆是否存在（初始化成功也返回 True）
    """
    if memory_exists(user_id):
        return True

    return initialize_user_memory(user_id)


__all__ = [
    "initialize_user_memory",
    "ensure_user_memory",
]