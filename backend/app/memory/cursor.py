"""游标管理

管理记忆处理的游标位置，避免重复处理。

游标定义：
- 游标是一个消息 UUID（last_memory_message_uuid）
- 记录上次记忆处理的位置
- Memory Agent 只处理游标之后的新消息

存储方式：
- 使用 Redis 存储（Key: memory_cursor:{user_id}:{conversation_id}）
- 无 TTL（跟随对话生命周期）
"""

from typing import Optional

from langchain_core.messages import BaseMessage

from app.infrastructure.persistence.redis import get_redis_client
from app.infrastructure.common.logger import logger


# ==================== 游标存储 ====================


def get_cursor_key(user_id: str, conversation_id: str) -> str:
    """生成游标的 Redis Key

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID

    Returns:
        Redis Key
    """
    return f"memory_cursor:{user_id}:{conversation_id}"


def get_cursor(user_id: str, conversation_id: str) -> Optional[str]:
    """获取当前游标位置

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID

    Returns:
        游标 UUID，不存在时返回 None
    """
    redis_client = get_redis_client()
    key = get_cursor_key(user_id, conversation_id)

    try:
        cursor = redis_client.client.get(key)
        return cursor
    except Exception as e:
        logger.error(f"Failed to get cursor: {e}")
        return None


def save_cursor(user_id: str, conversation_id: str, cursor_uuid: str) -> bool:
    """保存游标位置

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID
        cursor_uuid: 游标 UUID（最新消息的 UUID）

    Returns:
        是否成功
    """
    redis_client = get_redis_client()
    key = get_cursor_key(user_id, conversation_id)

    try:
        # 不设置 TTL，跟随对话生命周期
        redis_client.client.set(key, cursor_uuid)
        logger.info(
            f"Cursor saved: user_id={user_id}, "
            f"conversation_id={conversation_id}, cursor_uuid={cursor_uuid}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save cursor: {e}")
        return False


def delete_cursor(user_id: str, conversation_id: str) -> bool:
    """删除游标

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID

    Returns:
        是否成功
    """
    redis_client = get_redis_client()
    key = get_cursor_key(user_id, conversation_id)

    try:
        redis_client.client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Failed to delete cursor: {e}")
        return False


# ==================== 消息过滤 ====================


def get_messages_since_cursor(
    messages: list[BaseMessage],
    cursor_uuid: Optional[str],
) -> list[BaseMessage]:
    """获取游标后的新消息

    Args:
        messages: 消息列表
        cursor_uuid: 游标 UUID

    Returns:
        游标后的消息列表（游标不存在时返回全部消息）
    """
    if not messages:
        return []

    # 游标不存在，返回全部消息
    if not cursor_uuid:
        return messages

    # 找到游标位置
    cursor_index = -1
    for i, msg in enumerate(messages):
        msg_uuid = getattr(msg, "id", None) or getattr(msg, "uuid", None)
        if msg_uuid == cursor_uuid:
            cursor_index = i
            break

    # 未找到游标，返回全部消息
    if cursor_index == -1:
        logger.warning(f"Cursor UUID {cursor_uuid} not found in messages")
        return messages

    # 返回游标后的消息
    return messages[cursor_index + 1 :]


def get_last_message_uuid(messages: list[BaseMessage]) -> Optional[str]:
    """获取最后一条消息的 UUID

    Args:
        messages: 消息列表

    Returns:
        最后一条消息的 UUID，不存在时返回 None
    """
    if not messages:
        return None

    last_msg = messages[-1]
    return getattr(last_msg, "id", None) or getattr(last_msg, "uuid", None)


# ==================== 游标互斥检查 ====================


def has_memory_writes_since(
    messages: list[BaseMessage],
    cursor_uuid: Optional[str],
) -> bool:
    """检查游标后是否有主 Agent 记忆写入

    主 Agent 可以直接写入记忆（如用户明确要求"记住我喜欢..."）。
    主 Agent 写入时会在响应中添加 `<memory_write>` 标记。
    Memory Agent 检测到此标记后跳过处理。

    Args:
        messages: 消息列表
        cursor_uuid: 游标 UUID

    Returns:
        是否有主 Agent 记忆写入
    """
    # 获取游标后的消息
    new_messages = get_messages_since_cursor(messages, cursor_uuid)

    if not new_messages:
        return False

    # 检查 assistant 消息是否有 memory_write 标记
    for msg in new_messages:
        msg_type = getattr(msg, "type", "")
        if msg_type == "ai" or msg_type == "assistant":
            content = getattr(msg, "content", "")
            if "<memory_write>" in content:
                logger.info("Main agent memory write detected, skipping memory agent")
                return True

    return False


__all__ = [
    "get_cursor",
    "save_cursor",
    "delete_cursor",
    "get_messages_since_cursor",
    "get_last_message_uuid",
    "has_memory_writes_since",
]