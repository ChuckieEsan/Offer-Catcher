"""Memory Retrieval Service - Infrastructure 层

记忆检索服务，负责：
- 计算 embedding
- 检索 session_summaries
- 更新 checkpoint.memory_context
- 去重 + 容量控制
- 检索锁（并发控制）

作为 Infrastructure 层组件，直接操作数据库和 Checkpointer。
"""

import asyncio
from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.infrastructure.common.logger import logger
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
from app.infrastructure.persistence.postgres import get_checkpointer
from app.infrastructure.persistence.postgres.session_summary_repository import get_session_summary_repository
from app.infrastructure.persistence.postgres.conversation_repository import get_conversation_repository
from app.infrastructure.persistence.redis.client import get_redis_client
from app.infrastructure.config.settings import get_settings


# ==================== Retrieval Lock ====================

def get_retrieval_lock_key(user_id: str, conversation_id: str) -> str:
    """获取检索锁的 Redis key

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识

    Returns:
        Redis key
    """
    return f"retrieval_lock:{user_id}:{conversation_id}"


def acquire_retrieval_lock(user_id: str, conversation_id: str) -> bool:
    """获取检索锁

    使用 Redis SETNX 实现分布式锁，防止同一对话的并发检索。

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识

    Returns:
        True 表示成功获取锁，False 表示锁已被占用
    """
    redis_client = get_redis_client()
    key = get_retrieval_lock_key(user_id, conversation_id)

    # SETNX + TTL: 30秒超时自动释放
    result = redis_client.client.set(key, "1", nx=True, ex=30)
    if result:
        logger.debug(f"Retrieval lock acquired: {key}")
        return True
    else:
        logger.debug(f"Retrieval lock already held: {key}")
        return False


def release_retrieval_lock(user_id: str, conversation_id: str) -> None:
    """释放检索锁

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
    """
    redis_client = get_redis_client()
    key = get_retrieval_lock_key(user_id, conversation_id)
    redis_client.client.delete(key)
    logger.debug(f"Retrieval lock released: {key}")


def is_retrieval_in_progress(user_id: str, conversation_id: str) -> bool:
    """检查检索是否正在进行

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识

    Returns:
        True 表示检索正在进行
    """
    redis_client = get_redis_client()
    key = get_retrieval_lock_key(user_id, conversation_id)
    return redis_client.client.exists(key) > 0


# ==================== Retrieval Service ====================

async def retrieve_and_update_checkpoint(
    user_id: str,
    conversation_id: str,
    query: str,
) -> None:
    """异步检索记忆并更新 checkpoint

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        query: 用户提问文本
    """
    # 尝试获取锁
    if not acquire_retrieval_lock(user_id, conversation_id):
        logger.debug(f"Retrieval skipped: lock not acquired for {conversation_id}")
        return

    try:
        await _do_retrieval(user_id, conversation_id, query)
    except Exception as e:
        logger.error(f"Memory retrieval failed: {e}", exc_info=True)
    finally:
        release_retrieval_lock(user_id, conversation_id)


async def _do_retrieval(
    user_id: str,
    conversation_id: str,
    query: str,
) -> None:
    """执行检索逻辑

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        query: 用户提问文本
    """
    settings = get_settings()
    top_k = settings.memory_retrieval_top_k or 5
    max_size = settings.memory_context_max_size or 20 * 1024  # 20kb

    # 1. 计算 embedding
    embedding_adapter = get_embedding_adapter()
    query_embedding = embedding_adapter.embed(query)

    # 2. 语义检索 session_summaries
    repo = get_session_summary_repository()
    results = repo.search_by_embedding(user_id, query_embedding, top_k)

    if not results:
        logger.debug(f"No session summaries found for query: {query[:50]}")
        return

    # 3. 获取对话标题
    conv_repo = get_conversation_repository()
    enriched_results = []

    for r in results:
        conv = conv_repo.find_by_id(user_id, r.conversation_id)
        if conv:
            enriched_results.append({
                "conversation_id": r.conversation_id,
                "title": conv.title,
                "created_at": r.created_at.strftime("%Y-%m-%d"),
                "summary": r.summary,
            })

    if not enriched_results:
        return

    # 4. 更新 checkpoint
    async with get_checkpointer() as checkpointer:
        config = {"configurable": {"thread_id": conversation_id}}

        # 获取当前 checkpoint
        current_checkpoint = await checkpointer.aget(config)

        if current_checkpoint:
            # 读取现有 memory_context 和 injected_ids
            current_memory = current_checkpoint.channel_values.get("memory_context", "")
            injected_ids = current_checkpoint.channel_values.get("injected_session_ids", [])

            # 合并新结果（去重 + 容量控制）
            merged_context, merged_ids = merge_memory_context(
                current_memory,
                injected_ids,
                enriched_results,
                max_size,
            )

            # 更新 checkpoint
            current_checkpoint.channel_values["memory_context"] = merged_context
            current_checkpoint.channel_values["injected_session_ids"] = merged_ids

            await checkpointer.aput(config, current_checkpoint)
            logger.info(f"Memory context updated: {len(merged_ids)} sessions, {len(merged_context)} bytes")


def merge_memory_context(
    current_memory: str,
    injected_ids: list[str],
    new_results: list[dict],
    max_size: int,
) -> tuple[str, list[str]]:
    """合并记忆上下文（去重 + 容量控制）

    Args:
        current_memory: 当前 memory_context
        injected_ids: 已注入的 conversation_id 列表
        new_results: 新检索结果
        max_size: 最大容量（字节）

    Returns:
        (merged_context, merged_ids)
    """
    merged_ids = list(injected_ids)  # 复制列表
    new_sections = []

    # 去重：只添加未注入的 conversation_id
    for r in new_results:
        conv_id = r["conversation_id"]
        if conv_id not in merged_ids:
            merged_ids.append(conv_id)
            section = format_session_summary(r)
            new_sections.append(section)

    if not new_sections:
        return current_memory, merged_ids

    # 合并：新内容追加到现有内容
    if current_memory:
        merged_context = current_memory + "\n\n" + "\n\n".join(new_sections)
    else:
        merged_context = "\n\n".join(new_sections)

    # 容量控制：超过上限时裁剪最早的内容
    if len(merged_context.encode("utf-8")) > max_size:
        # 从开头裁剪，保留最新的
        sections = merged_context.split("\n\n### ")
        while len(merged_context.encode("utf-8")) > max_size and len(sections) > 1 and len(merged_ids) > 1:
            sections.pop(0)
            merged_ids.pop(0)
            merged_context = "### " + "\n\n### ".join(sections) if sections else ""

    return merged_context, merged_ids


def format_session_summary(result: dict) -> str:
    """格式化单个会话摘要

    Args:
        result: 会话摘要数据

    Returns:
        Markdown 格式的摘要
    """
    title = result.get("title", "未知对话")
    created_at = result.get("created_at", "")
    summary = result.get("summary", "")

    return f"### {title} ({created_at})\n{summary}"


def trigger_retrieval(
    user_id: str,
    conversation_id: str,
    query: str,
) -> None:
    """触发异步检索（fire-and-forget）

    检查触发条件后启动检索任务。

    Args:
        user_id: 用户唯一标识
        conversation_id: 对话唯一标识
        query: 用户提问文本
    """
    # 检查触发条件
    settings = get_settings()
    min_length = settings.memory_retrieval_min_length or 10

    if not query or len(query.strip()) < min_length:
        logger.debug(f"Retrieval not triggered: query too short")
        return

    # Fire-and-forget
    asyncio.create_task(retrieve_and_update_checkpoint(user_id, conversation_id, query))
    logger.debug(f"Memory retrieval triggered for conversation {conversation_id}")


__all__ = [
    # Lock functions
    "get_retrieval_lock_key",
    "acquire_retrieval_lock",
    "release_retrieval_lock",
    "is_retrieval_in_progress",
    # Retrieval functions
    "retrieve_and_update_checkpoint",
    "merge_memory_context",
    "format_session_summary",
    "trigger_retrieval",
]