"""对话结束时的 Hooks

在对话结束后触发记忆 Agent，更新用户记忆。

设计要点：
- 对话结束后异步调用 Memory Agent
- 不阻塞主流程（记忆是增强功能）
- 使用游标机制避免重复处理
- 游标互斥保证主 Agent 写入不被覆盖

实现方式：
- 在 API 层面，对话结束后调用 memory agent
- 使用 asyncio.create_task 异步执行（fire-and-forget）
"""

import asyncio
from typing import Optional

from langchain_core.messages import BaseMessage

from app.memory.agent.agent import run_memory_agent
from app.utils.logger import logger


async def trigger_memory_update(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> None:
    """触发记忆更新（异步，不阻塞主流程）

    在对话结束后调用，启动 Memory Agent 分析对话并更新记忆。
    使用 asyncio.create_task 实现 fire-and-forget。

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID
        messages: 完整的消息列表
    """
    if not user_id or not conversation_id:
        logger.warning("Missing user_id or conversation_id, skipping memory update")
        return

    if not messages:
        logger.warning("No messages to process, skipping memory update")
        return

    # 使用 create_task 异步执行（不阻塞）
    # 注意：这里不等待结果，记忆更新是增强功能
    task = asyncio.create_task(
        _run_memory_update_safe(user_id, conversation_id, messages)
    )

    # 添加回调用于日志记录
    task.add_done_callback(_log_memory_update_result)

    logger.info(
        f"Memory update triggered: user_id={user_id}, "
        f"conversation_id={conversation_id}, message_count={len(messages)}"
    )


async def _run_memory_update_safe(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> bool:
    """安全执行记忆更新（带异常处理）

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID
        messages: 消息列表

    Returns:
        是否成功
    """
    try:
        await run_memory_agent(user_id, conversation_id, messages)
        return True
    except Exception as e:
        logger.error(
            f"Memory update failed: user_id={user_id}, "
            f"conversation_id={conversation_id}, error={e}"
        )
        return False


def _log_memory_update_result(task: asyncio.Task) -> None:
    """记录记忆更新结果（回调函数）

    Args:
        task: asyncio Task
    """
    try:
        result = task.result()
        if result:
            logger.debug("Memory update completed successfully")
        else:
            logger.warning("Memory update completed with errors")
    except Exception as e:
        logger.error(f"Memory update task failed: {e}")


# ==================== 同步版本（用于测试） ====================


async def trigger_memory_update_sync(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> bool:
    """触发记忆更新（同步，等待结果）

    用于测试场景，等待 Memory Agent 完成后返回结果。

    Args:
        user_id: 用户 ID
        conversation_id: 对话 ID
        messages: 消息列表

    Returns:
        是否成功
    """
    return await _run_memory_update_safe(user_id, conversation_id, messages)


__all__ = [
    "trigger_memory_update",
    "trigger_memory_update_sync",
]