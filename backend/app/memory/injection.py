"""记忆注入逻辑

负责将用户记忆注入到 Agent 的上下文中。

设计要点：
- MEMORY.md 始终加载，注入到 System Prompt
- session_summaries 按需检索（语义检索历史）
- memory_context 容量控制（不超过 20KB）

使用方式：
    from app.memory import build_memory_context, inject_memory_context
    memory_context = build_memory_context(user_id, query)
    inject_memory_context(user_id, messages)
"""

from langchain_core.messages import BaseMessage, SystemMessage

from app.config.settings import get_settings
from app.infrastructure.persistence.postgres import get_postgres_client
from app.memory.io import read_memory, memory_exists
from app.memory.init import ensure_user_memory
from app.memory.store import get_memory_store
from app.tools.embedding_tool import get_embedding_tool
from app.utils.logger import logger


# ==================== 记忆上下文构建 ====================


def build_memory_context(
    user_id: str,
    query: str | None = None,
) -> str:
    """构建记忆上下文

    组合 MEMORY.md + 语义检索的 session_summaries。

    Args:
        user_id: 用户 ID
        query: 当前查询（用于语义检索相关历史，可选）

    Returns:
        记忆上下文字符串
    """
    try:
        memory_store = get_memory_store()
        if not memory_store.initialized:
            logger.warning("MemoryStore not initialized, returning empty context")
            return ""

        # 确保用户记忆存在
        ensure_user_memory(user_id)

        # 读取 MEMORY.md（始终包含）
        memory_content = read_memory(user_id)
        if not memory_content:
            return ""

        # 如果有查询，语义检索相关历史
        session_context = ""
        if query and len(query) >= 10:  # 最小查询长度
            session_context = _search_relevant_sessions(user_id, query)

        # 组合上下文
        context_parts = [f"<用户记忆>\n{memory_content}\n</用户记忆>"]

        if session_context:
            context_parts.append(f"\n\n<相关历史>\n{session_context}\n</相关历史>")

        full_context = "\n".join(context_parts)

        # 容量控制
        settings = get_settings()
        max_size = settings.memory_context_max_size  # 默认 20KB
        if len(full_context.encode("utf-8")) > max_size:
            full_context = _truncate_context(full_context, max_size)

        return full_context

    except Exception as e:
        logger.warning(f"Failed to build memory context: {e}")
        return ""


def _search_relevant_sessions(user_id: str, query: str) -> str:
    """语义检索相关会话历史

    Args:
        user_id: 用户 ID
        query: 查询文本

    Returns:
        格式化的会话历史字符串
    """
    try:
        # 计算 embedding
        embedding_tool = get_embedding_tool()
        query_embedding = embedding_tool.embed_text(query)

        # 语义检索
        pg_client = get_postgres_client()
        settings = get_settings()
        top_k = settings.memory_retrieval_top_k  # 默认 5

        results = pg_client.search_session_summaries(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        if not results:
            return ""

        # 格式化输出
        output_lines = []
        for r in results:
            conv = pg_client.get_conversation(user_id, r.conversation_id)
            title = conv.title if conv else "未知对话"
            created_at = conv.created_at.strftime("%Y-%m-%d") if conv else ""

            output_lines.append(f"- {title} ({created_at})")
            output_lines.append(f"  摘要：{r.summary}")

        return "\n".join(output_lines)

    except Exception as e:
        logger.warning(f"Failed to search relevant sessions: {e}")
        return ""


def _truncate_context(context: str, max_size: int) -> str:
    """截断记忆上下文

    Args:
        context: 记忆上下文
        max_size: 最大字节数

    Returns:
        截断后的上下文
    """
    # 简单截断策略：保留 MEMORY.md，裁剪历史部分
    lines = context.split("\n")
    truncated = []

    # 找到 <用户记忆> 部分，完整保留
    in_memory = False
    for line in lines:
        if "<用户记忆>" in line:
            in_memory = True
        if in_memory:
            truncated.append(line)
            if "</用户记忆>" in line:
                break

    # 添加截断提示
    truncated.append("\n\n<!-- 记忆上下文已截断以适应容量限制 -->")

    result = "\n".join(truncated)

    # 再次检查，如果仍然超限则进一步裁剪
    while len(result.encode("utf-8")) > max_size and len(truncated) > 10:
        truncated = truncated[: len(truncated) // 2]
        truncated.append("\n\n<!-- 记忆上下文已截断 -->")
        result = "\n".join(truncated)

    return result


# ==================== 记忆注入 ====================


def inject_memory_context(
    user_id: str,
    messages: list[BaseMessage],
) -> str:
    """注入用户记忆上下文到消息列表

    将 MEMORY.md 注入到第一条 SystemMessage 中。
    如果没有 SystemMessage，会在开头添加一条。

    Args:
        user_id: 用户 ID
        messages: 消息列表（会被修改）

    Returns:
        注入的记忆内容（用于日志记录）
    """
    try:
        memory_store = get_memory_store()
        if not memory_store.initialized:
            logger.warning("MemoryStore not initialized, skipping memory injection")
            return ""

        # 确保用户记忆存在
        ensure_user_memory(user_id)

        # 构建记忆上下文
        memory_context = build_memory_context(user_id)

        if not memory_context:
            return ""

        # 找到第一条 SystemMessage 并追加记忆上下文
        for i, msg in enumerate(messages):
            if getattr(msg, "type", "") == "system":
                original_content = getattr(msg, "content", "")
                # 避免重复注入
                if "<用户记忆>" not in original_content:
                    new_content = original_content + "\n\n" + memory_context
                    messages[i] = SystemMessage(content=new_content)
                    logger.info(
                        f"Injected memory context for user {user_id} "
                        f"({len(memory_context)} chars)"
                    )
                return memory_context

        # 如果没有 SystemMessage，在开头添加
        messages.insert(0, SystemMessage(content=memory_context))
        logger.info(
            f"Injected memory context for user {user_id} "
            f"({len(memory_context)} chars) - added new SystemMessage"
        )

        return memory_context

    except Exception as e:
        logger.warning(f"Failed to inject memory context: {e}")
        return ""


__all__ = [
    "build_memory_context",
    "inject_memory_context",
]