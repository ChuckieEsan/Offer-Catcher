"""Memory Agent Tools

定义记忆管理 Agent 使用的工具。
使用 @tool 装饰器定义 LangChain Tools。

工具列表：
- write_session_summary: 写入会话摘要
- update_preferences: 更新偏好设置
- update_behaviors: 更新行为模式
- update_memory_index: 更新 MEMORY.md 概要

注意：游标更新由确定性代码执行，不作为 Agent Tool。
"""

import uuid

from langchain_core.tools import tool

from app.infrastructure.common.logger import logger
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter


@tool
def write_session_summary(
    summary: str,
    conversation_id: str,
    user_id: str,
    importance: str = "medium",
    topics: str = "",
    memory_layer: str = "short_term",
) -> str:
    """写入会话摘要到 session_summaries 表。

    Args:
        summary: 会话摘要（简洁描述关键内容，20-50字）
        conversation_id: 对话 ID
        user_id: 用户 ID
        importance: 重要性评级（high/medium/low），根据讨论深度判断
        topics: 话题标签（逗号分隔，如 "rabbitmq,kafka,消息队列")
        memory_layer: 记忆层级（long_term/short_term），高重要性用 long_term

    Returns:
        操作结果消息
    """
    from app.infrastructure.persistence.postgres import get_session_summary_repository
    from app.domain.memory.aggregates import MemoryLayer

    repo = get_session_summary_repository()

    # 计算 embedding
    embedding_adapter = get_embedding_adapter()
    embedding = embedding_adapter.embed(summary)

    # 重要性映射
    importance_map = {"high": 0.8, "medium": 0.5, "low": 0.3}
    importance_score = importance_map.get(importance, 0.5)

    # 解析话题
    topics_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else []

    # 层级映射
    layer = MemoryLayer.LTM if memory_layer == "long_term" else MemoryLayer.STM

    # 创建摘要
    session_summary_id = str(uuid.uuid4())
    from app.domain.memory.aggregates import SessionSummary

    summary_entity = SessionSummary.create(
        id=session_summary_id,
        conversation_id=conversation_id,
        user_id=user_id,
        summary=summary,
        embedding=embedding,
        importance_score=importance_score,
        topics=topics_list,
        memory_layer=layer,
    )

    repo.create(summary_entity)
    logger.info(f"Session summary written: {session_summary_id}, importance={importance_score}, layer={memory_layer}")

    return f"会话摘要已写入: {session_summary_id} (重要性:{importance}, 层级:{memory_layer})"


@tool
def update_preferences(content: str, user_id: str) -> str:
    """更新 preferences.md 文件。

    Args:
        content: 完整的 preferences.md 内容
        user_id: 用户 ID

    Returns:
        操作结果消息
    """
    from app.infrastructure.persistence.postgres import get_memory_repository

    with get_memory_repository() as repo:
        repo.write_reference(user_id, "preferences", content)

    logger.info(f"preferences.md updated for user {user_id}")
    return "preferences.md 已更新"


@tool
def update_behaviors(content: str, user_id: str) -> str:
    """更新 behaviors.md 文件。

    Args:
        content: 完整的 behaviors.md 内容
        user_id: 用户 ID

    Returns:
        操作结果消息
    """
    from app.infrastructure.persistence.postgres import get_memory_repository

    with get_memory_repository() as repo:
        repo.write_reference(user_id, "behaviors", content)

    logger.info(f"behaviors.md updated for user {user_id}")
    return "behaviors.md 已更新"


@tool
def update_memory_index(user_id: str) -> str:
    """更新 MEMORY.md 概要，同步 preferences 和 behaviors 的概要信息。

    Args:
        user_id: 用户 ID

    Returns:
        操作结果消息
    """
    from app.infrastructure.persistence.postgres import (
        get_memory_repository,
        get_session_summary_repository,
    )

    with get_memory_repository() as repo:
        # 获取当前内容
        preferences = repo.read_reference(user_id, "preferences")
        behaviors = repo.read_reference(user_id, "behaviors")

        # 获取最近会话摘要
        summary_repo = get_session_summary_repository()
        recent_sessions = summary_repo.get_recent(user_id, limit=5)

        # 构建 MEMORY.md 内容
        memory_content = _build_memory_content(
            user_id, preferences, behaviors, recent_sessions
        )

        repo.write_content(user_id, memory_content)

    logger.info(f"MEMORY.md index updated for user {user_id}")
    return "MEMORY.md 概要已更新"


def _build_memory_content(
    user_id: str,
    preferences: str | None,
    behaviors: str | None,
    recent_sessions: list,
) -> str:
    """构建 MEMORY.md 内容"""
    # 解析偏好概要
    prefs_summary = _extract_prefs_summary(preferences)

    # 解析行为概要
    behaviors_summary = _extract_behaviors_summary(behaviors)

    # 构建会话历史概要
    sessions_summary = _build_sessions_summary(recent_sessions)

    # 组合内容
    content = f"""---
name: user-memory-{user_id}
description: 用户特定的偏好和行为规则。始终加载此文档。
             当概要信息不足以回答问题时，使用 load_memory_reference Tool
             或 search_session_history Tool 查询详情。
---

# 用户记忆

## 偏好概要
{prefs_summary}

## 行为模式概要
{behaviors_summary}

## 会话历史概要
{sessions_summary}

## 可用 References
| Reference | 描述 | 建议调用时机 |
|-----------|------|-------------|
| `preferences` | 完整的用户偏好设置 | 用户表达反馈 |
| `behaviors` | 观察到的行为模式详情 | Agent 调整响应策略 |

## 可用自定义 Skill
（暂无自定义 Skill，可通过 UI 创建）

## 使用指南
1. 本文档始终加载，提供概要信息
2. 概要不够详细时，调用 `load_memory_reference` 加载详情
3. 需要语义检索历史时，调用 `search_session_history` 搜索
4. 触发自定义 Skill 时，调用 `load_skill` 加载
"""
    return content


def _extract_prefs_summary(preferences: str | None) -> str:
    """从 preferences.md 提取概要"""
    if not preferences:
        return "- 语言：中文\n- 解释深度：适中\n- 代码示例：根据问题需要"

    # 简单提取响应风格部分的前几行
    lines = preferences.split("\n")
    summary_lines = []
    for line in lines:
        if line.startswith("## ") or line.startswith("- "):
            summary_lines.append(line)
        if len(summary_lines) >= 5:
            break

    return "\n".join(summary_lines) if summary_lines else "- 语言：中文"


def _extract_behaviors_summary(behaviors: str | None) -> str:
    """从 behaviors.md 提取概要"""
    if not behaviors:
        return "（暂无观察到的行为模式）"

    # 提取主要行为模式
    lines = behaviors.split("\n")
    summary_lines = []
    for line in lines:
        if line.startswith("## ") or line.startswith("用户"):
            summary_lines.append(line)
        if len(summary_lines) >= 4:
            break

    return "\n".join(summary_lines) if summary_lines else "（暂无观察到的行为模式）"


def _build_sessions_summary(recent_sessions: list) -> str:
    """构建会话历史概要"""
    if not recent_sessions:
        return "（暂无历史会话）"

    lines = ["最近 5 次会话："]
    for session in recent_sessions:
        created_at = session.created_at.strftime("%Y-%m-%d")
        summary_short = session.summary[:50] if len(session.summary) > 50 else session.summary
        lines.append(f"- {created_at} | {summary_short}")

    return "\n".join(lines)


__all__ = [
    "write_session_summary",
    "update_preferences",
    "update_behaviors",
    "update_memory_index",
]