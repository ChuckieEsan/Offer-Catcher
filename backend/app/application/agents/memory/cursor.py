"""Memory Cursor Management

管理记忆处理游标，实现：
- 游标存储（Redis）
- 游标互斥检查

游标定义：last_memory_message_uuid 是一个消息 UUID，记录上次处理的位置。
"""

from app.infrastructure.persistence.redis import get_redis_client
from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


def get_cursor_key(user_id: str, conversation_id: str) -> str:
    """获取游标的 Redis key

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识

    Returns:
        Redis key: memory_cursor:{user_id}:{conversation_id}
    """
    return f"memory_cursor:{user_id}:{conversation_id}"


def save_cursor(user_id: str, conversation_id: str, cursor_uuid: str) -> None:
    """保存游标位置

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        cursor_uuid: 最新处理的消息 UUID
    """
    redis_client = get_redis_client()
    key = get_cursor_key(user_id, conversation_id)

    settings = get_settings()
    ttl = settings.redis_ttl

    redis_client.set(key, cursor_uuid, ex=ttl)
    logger.debug(f"Cursor saved: {key} -> {cursor_uuid}")


def get_cursor(user_id: str, conversation_id: str) -> str | None:
    """获取游标位置

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识

    Returns:
        上次处理的消息 UUID，不存在时返回 None
    """
    redis_client = get_redis_client()
    key = get_cursor_key(user_id, conversation_id)

    cursor = redis_client.get(key)
    if cursor:
        return cursor.decode("utf-8")
    return None


def has_memory_writes_since(
    messages: list,
    since_uuid: str,
) -> bool:
    """检查游标之后是否有主 Agent 记忆写入

    游标互斥机制：主 Agent 直接写入记忆时，在响应中添加 <memory_write> 标记。
    后台 Agent 检查此标记，发现后跳过处理。

    Args:
        messages: LangChain 消息列表（BaseMessage）
        since_uuid: 上次处理的消息 UUID

    Returns:
        是否有记忆写入标记
    """
    found_start = False

    for msg in messages:
        # 找到游标位置
        if not found_start:
            msg_uuid = getattr(msg, "id", None) or getattr(msg, "uuid", None)
            if msg_uuid == since_uuid:
                found_start = True
            continue

        # 只检查游标之后的 assistant 消息
        msg_type = getattr(msg, "type", "")
        if msg_type == "ai" or msg_type == "assistant":
            content = getattr(msg, "content", "")
            # 检查是否有记忆写入标记
            if "<memory_write>" in content:
                logger.info("Memory write marker found, skipping background update")
                return True

    return False


def get_messages_since_cursor(
    messages: list,
    cursor_uuid: str | None,
) -> list:
    """获取游标之后的新消息

    Args:
        messages: LangChain 消息列表
        cursor_uuid: 游标位置（None 表示从头开始）

    Returns:
        游标之后的消息列表
    """
    if cursor_uuid is None:
        return messages

    found_start = False
    new_messages = []

    for msg in messages:
        if not found_start:
            msg_uuid = getattr(msg, "id", None) or getattr(msg, "uuid", None)
            if msg_uuid == cursor_uuid:
                found_start = True
            continue

        new_messages.append(msg)

    return new_messages


__all__ = [
    "get_cursor_key",
    "save_cursor",
    "get_cursor",
    "has_memory_writes_since",
    "get_messages_since_cursor",
]