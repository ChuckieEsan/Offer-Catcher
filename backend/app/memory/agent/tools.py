"""记忆操作 Tools

Memory Agent 专用的工具，用于写入和更新用户记忆。

工具列表：
- write_session_summary: 写入会话摘要到数据库（含 embedding）
- update_preferences: 更新 preferences.md 文件
- update_behaviors: 更新 behaviors.md 文件
- update_memory_index: 更新 MEMORY.md 概要
- update_cursor: 更新游标位置

设计要点：
- 使用 @tool 装饰器创建 LangChain tools
- 每个工具负责具体的写入操作
- Memory Agent 自主决定调用哪些工具
"""

from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field

from app.db.postgres_client import get_postgres_client
from app.memory.io import (
    write_memory,
    write_memory_reference,
    read_memory_reference,
)
from app.memory.cursor import save_cursor
from app.tools.embedding_tool import get_embedding_tool
from app.tools.context import UserContext
from app.utils.logger import logger


# ==================== 输入模型 ====================


class WriteSessionSummaryInput(BaseModel):
    """write_session_summary 工具的输入参数"""

    summary: str = Field(
        description="会话摘要（简洁描述关键内容，如'用户询问了 RAG 的召回阈值设置'）"
    )
    conversation_id: str = Field(description="对话 ID")
    user_id: str = Field(description="用户 ID")


class UpdatePreferencesInput(BaseModel):
    """update_preferences 工具的输入参数"""

    content: str = Field(
        description="完整的 preferences.md 内容（整合现有内容和新反馈）"
    )
    user_id: str = Field(description="用户 ID")


class UpdateBehaviorsInput(BaseModel):
    """update_behaviors 工具的输入参数"""

    content: str = Field(
        description="完整的 behaviors.md 内容（整合现有内容和新观察）"
    )
    user_id: str = Field(description="用户 ID")


class UpdateMemoryIndexInput(BaseModel):
    """update_memory_index 工具的输入参数"""

    user_id: str = Field(description="用户 ID")


class UpdateCursorInput(BaseModel):
    """update_cursor 工具的输入参数"""

    conversation_id: str = Field(description="对话 ID")
    user_id: str = Field(description="用户 ID")
    cursor_uuid: str = Field(description="最新消息的 UUID")


# ==================== Tool 实现 ====================


@tool(args_schema=WriteSessionSummaryInput)
def write_session_summary(
    summary: str,
    conversation_id: str,
    user_id: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """写入会话摘要到数据库（用于语义检索历史）。

    在对话结束且有值得记录的内容时调用。
    摘要将自动计算 embedding 并存储到 session_summaries 表。

    Args:
        summary: 会话摘要（简洁描述关键内容）
        conversation_id: 对话 ID
        user_id: 用户 ID

    Returns:
        写入结果信息
    """
    try:
        # 1. 计算 embedding
        embedding_tool = get_embedding_tool()
        embedding = embedding_tool.embed_text(summary)

        # 2. 写入数据库
        pg_client = get_postgres_client()
        pg_client.create_session_summary(
            conversation_id=conversation_id,
            user_id=user_id,
            summary=summary,
            embedding=embedding,
            session_type="chat",
        )

        logger.info(
            f"Session summary written: conversation_id={conversation_id}, "
            f"user_id={user_id}"
        )

        return "会话摘要已写入数据库"

    except Exception as e:
        logger.error(f"write_session_summary failed: {e}")
        return f"写入会话摘要失败：{e}"


@tool(args_schema=UpdatePreferencesInput)
def update_preferences(
    content: str,
    user_id: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """更新用户偏好设置文件。

    在用户表达了偏好或反馈时调用。
    需要传入完整的 preferences.md 内容（整合现有内容和新反馈）。

    Args:
        content: 完整的 preferences.md 内容
        user_id: 用户 ID

    Returns:
        更新结果信息
    """
    try:
        write_memory_reference(user_id, "preferences", content)

        logger.info(f"preferences.md updated for user {user_id}")

        return "preferences.md 已更新"

    except Exception as e:
        logger.error(f"update_preferences failed: {e}")
        return f"更新 preferences.md 失败：{e}"


@tool(args_schema=UpdateBehaviorsInput)
def update_behaviors(
    content: str,
    user_id: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """更新用户行为模式文件。

    在观察到用户的行为模式时调用。
    需要传入完整的 behaviors.md 内容（整合现有内容和新观察）。

    Args:
        content: 完整的 behaviors.md 内容
        user_id: 用户 ID

    Returns:
        更新结果信息
    """
    try:
        write_memory_reference(user_id, "behaviors", content)

        logger.info(f"behaviors.md updated for user {user_id}")

        return "behaviors.md 已更新"

    except Exception as e:
        logger.error(f"update_behaviors failed: {e}")
        return f"更新 behaviors.md 失败：{e}"


@tool(args_schema=UpdateMemoryIndexInput)
def update_memory_index(
    user_id: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """更新 MEMORY.md 概要。

    在 preferences 或 behaviors 有更新时调用。
    同步最新的偏好和行为概要到 MEMORY.md 主文档。

    Args:
        user_id: 用户 ID

    Returns:
        更新结果信息
    """
    try:
        # 读取当前 preferences 和 behaviors
        preferences = read_memory_reference(user_id, "preferences")
        behaviors = read_memory_reference(user_id, "behaviors")

        # 获取最近的会话摘要
        pg_client = get_postgres_client()
        recent_sessions = pg_client.get_recent_session_summaries(user_id, limit=5)

        # 构建 MEMORY.md 概要内容
        # TODO: 这里可以进一步优化，使用 LLM 来生成更精炼的概要
        memory_content = build_memory_summary(
            preferences, behaviors, recent_sessions
        )

        write_memory(user_id, memory_content)

        logger.info(f"MEMORY.md index updated for user {user_id}")

        return "MEMORY.md 概要已更新"

    except Exception as e:
        logger.error(f"update_memory_index failed: {e}")
        return f"更新 MEMORY.md 概要失败：{e}"


@tool(args_schema=UpdateCursorInput)
def update_cursor(
    conversation_id: str,
    user_id: str,
    cursor_uuid: str,
    runtime: Annotated[ToolRuntime[UserContext], InjectedToolArg] = None,
) -> str:
    """更新游标位置（标记已处理到最新消息）。

    **必须最后调用**，标记本次记忆处理的完成位置。

    Args:
        conversation_id: 对话 ID
        user_id: 用户 ID
        cursor_uuid: 最新消息的 UUID

    Returns:
        更新结果信息
    """
    try:
        save_cursor(user_id, conversation_id, cursor_uuid)

        logger.info(
            f"Cursor updated: conversation_id={conversation_id}, "
            f"user_id={user_id}, cursor_uuid={cursor_uuid}"
        )

        return "游标已更新"

    except Exception as e:
        logger.error(f"update_cursor failed: {e}")
        return f"更新游标失败：{e}"


# ==================== 辅助函数 ====================


def build_memory_summary(
    preferences: str,
    behaviors: str,
    recent_sessions: list,
) -> str:
    """构建 MEMORY.md 概要内容

    Args:
        preferences: preferences.md 内容
        behaviors: behaviors.md 内容
        recent_sessions: 最近会话摘要列表

    Returns:
        MEMORY.md 内容
    """
    # 从 preferences 提取概要
    prefs_lines = preferences.split("\n")
    prefs_summary = []
    for line in prefs_lines:
        if line.startswith("## 响应风格") or line.startswith("- "):
            prefs_summary.append(line)
        if len(prefs_summary) >= 5:
            break

    # 从 behaviors 提取概要
    behav_lines = behaviors.split("\n")
    behav_summary = []
    for line in behav_lines:
        if line.startswith("## ") or line.startswith("**建议**"):
            behav_summary.append(line)
        if len(behav_summary) >= 4:
            break

    # 构建会话历史概要
    session_summary = []
    for session in recent_sessions[:5]:
        date_str = session.created_at.strftime("%Y-%m-%d")
        session_summary.append(f"- {date_str} | {session.title}")

    # 组装 MEMORY.md 内容
    memory_content = f"""---
name: user-memory
description: 用户特定的偏好和行为规则。始终加载此文档。
---

# 用户记忆

## 偏好概要
{chr(10).join(prefs_summary[:5]) if prefs_summary else '- 语言：中文'}

## 行为模式概要
{chr(10).join(behav_summary[:4]) if behav_summary else '(暂无观察到的行为模式)'}
{'(暂无观察到的行为模式)' if not behav_summary else ''}

## 会话历史概要
最近 5 次会话：
{chr(10).join(session_summary) if session_summary else '(暂无历史会话)'}

## 可用 References
| Reference | 描述 | 建议调用时机 |
|-----------|------|-------------|
| `preferences` | 完整的用户偏好设置 | 用户表达反馈 |
| `behaviors` | 观察到的行为模式详情 | Agent 调整响应策略 |
"""

    return memory_content


__all__ = [
    "write_session_summary",
    "update_preferences",
    "update_behaviors",
    "update_memory_index",
    "update_cursor",
    "WriteSessionSummaryInput",
    "UpdatePreferencesInput",
    "UpdateBehaviorsInput",
    "UpdateMemoryIndexInput",
    "UpdateCursorInput",
]