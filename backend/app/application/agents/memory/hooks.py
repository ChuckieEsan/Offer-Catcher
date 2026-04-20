"""Memory Hooks

实现 Stop Hook，在对话结束时触发记忆 Agent。
使用 fire-and-forget 模式，不阻塞主流程。
"""

import asyncio
from typing import Callable

from langchain_core.messages import BaseMessage

from app.infrastructure.common.logger import logger
from app.application.agents.memory.agent import run_memory_agent


def extract_memories(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> None:
    """提取记忆（fire-and-forget）

    在对话结束时触发记忆 Agent，异步执行，不阻塞主流程。

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        messages: LangChain 消息列表
    """
    # 使用 fire-and-forget 模式
    asyncio.create_task(
        run_memory_agent(user_id, conversation_id, messages)
    )
    logger.info(f"Memory extraction triggered for conversation {conversation_id}")


def create_memory_extraction_hook() -> Callable:
    """创建记忆提取 Hook

    返回一个 Hook 函数，可以在对话结束时调用。

    Returns:
        Hook 函数
    """
    return extract_memories


async def safe_extract_memories(
    user_id: str,
    conversation_id: str,
    messages: list[BaseMessage],
) -> None:
    """安全提取记忆（带异常处理）

    用于需要等待执行完成的场景。

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        messages: LangChain 消息列表
    """
    try:
        await run_memory_agent(user_id, conversation_id, messages)
    except Exception as e:
        logger.error(f"Safe memory extraction failed: {e}", exc_info=True)


__all__ = [
    "extract_memories",
    "create_memory_extraction_hook",
    "safe_extract_memories",
]