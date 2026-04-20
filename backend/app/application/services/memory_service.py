"""Memory Service - 记忆应用服务

编排记忆相关用例，调用 Infrastructure 层 Repository。
"""

from app.domain.memory.aggregates import Memory, MemoryReference
from app.infrastructure.persistence.postgres.memory_repository import get_memory_repository
from app.infrastructure.persistence.postgres.session_summary_repository import get_session_summary_repository
from app.infrastructure.common.logger import logger


class MemoryService:
    """记忆应用服务

    提供记忆相关的用例编排：
    - 获取用户记忆（MEMORY.md）
    - 获取偏好设置（preferences.md）
    - 获取行为模式（behaviors.md）
    """

    def get_memory(self, user_id: str) -> Memory | None:
        """获取用户记忆聚合

        Args:
            user_id: 用户唯一标识

        Returns:
            Memory 聚合根，不存在时返回 None
        """
        with get_memory_repository() as repo:
            memory = repo.find_by_user_id(user_id)
            if not memory:
                # 首次访问，初始化记忆
                memory = repo.initialize(user_id)
                logger.info(f"Memory initialized for user {user_id}")
            return memory

    def get_preferences(self, user_id: str) -> str:
        """获取用户偏好设置

        Args:
            user_id: 用户唯一标识

        Returns:
            preferences.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_reference(user_id, "preferences")
            if not content:
                # 首次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_reference(user_id, "preferences")
            return content or ""

    def get_behaviors(self, user_id: str) -> str:
        """获取用户行为模式

        Args:
            user_id: 用户唯一标识

        Returns:
            behaviors.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_reference(user_id, "behaviors")
            if not content:
                # 首次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_reference(user_id, "behaviors")
            return content or ""

    def get_memory_content(self, user_id: str) -> str:
        """获取 MEMORY.md 主文档内容

        Args:
            user_id: 用户唯一标识

        Returns:
            MEMORY.md 内容
        """
        with get_memory_repository() as repo:
            content = repo.read_content(user_id)
            if not content:
                # 馍次访问，初始化记忆
                repo.initialize(user_id)
                content = repo.read_content(user_id)
            return content or ""

    def update_preferences(self, user_id: str, content: str) -> None:
        """更新用户偏好设置并同步 MEMORY.md

        Args:
            user_id: 用户唯一标识
            content: preferences.md 内容（Markdown 格式）
        """
        with get_memory_repository() as repo:
            # 确保 memory 已初始化
            if not repo.read_content(user_id):
                repo.initialize(user_id)
            repo.write_reference(user_id, "preferences", content)
            logger.info(f"preferences.md updated for user {user_id}")

        # 同步 MEMORY.md 概要
        self._sync_memory_index(user_id)

    def update_behaviors(self, user_id: str, content: str) -> None:
        """更新用户行为模式并同步 MEMORY.md

        Args:
            user_id: 用户唯一标识
            content: behaviors.md 内容（Markdown 格式）
        """
        with get_memory_repository() as repo:
            # 确保 memory 已初始化
            if not repo.read_content(user_id):
                repo.initialize(user_id)
            repo.write_reference(user_id, "behaviors", content)
            logger.info(f"behaviors.md updated for user {user_id}")

        # 同步 MEMORY.md 概要
        self._sync_memory_index(user_id)

    def _sync_memory_index(self, user_id: str) -> None:
        """同步更新 MEMORY.md 概要

        根据 preferences 和 behaviors 的最新内容，
        重新生成 MEMORY.md 的概要部分。

        Args:
            user_id: 用户唯一标识
        """
        with get_memory_repository() as repo:
            # 获取当前内容
            preferences = repo.read_reference(user_id, "preferences")
            behaviors = repo.read_reference(user_id, "behaviors")

            # 获取最近会话摘要
            summary_repo = get_session_summary_repository()
            recent_sessions = summary_repo.get_recent(user_id, limit=5)

            # 构建 MEMORY.md 内容
            memory_content = self._build_memory_content(
                user_id, preferences, behaviors, recent_sessions
            )

            repo.write_content(user_id, memory_content)
            logger.info(f"MEMORY.md index synced for user {user_id}")

    def _build_memory_content(
        self,
        user_id: str,
        preferences: str | None,
        behaviors: str | None,
        recent_sessions: list,
    ) -> str:
        """构建 MEMORY.md 内容"""
        prefs_summary = self._extract_prefs_summary(preferences)
        behaviors_summary = self._extract_behaviors_summary(behaviors)
        sessions_summary = self._build_sessions_summary(recent_sessions)

        return f"""---
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

    def _extract_prefs_summary(self, preferences: str | None) -> str:
        """从 preferences.md 提取概要"""
        if not preferences:
            return "- 语言：中文\n- 解释深度：适中\n- 代码示例：根据问题需要"

        lines = preferences.split("\n")
        summary_lines = []
        for line in lines:
            if line.startswith("## ") or line.startswith("- "):
                summary_lines.append(line)
            if len(summary_lines) >= 5:
                break

        return "\n".join(summary_lines) if summary_lines else "- 语言：中文"

    def _extract_behaviors_summary(self, behaviors: str | None) -> str:
        """从 behaviors.md 提取概要"""
        if not behaviors:
            return "（暂无观察到的行为模式）"

        lines = behaviors.split("\n")
        summary_lines = []
        for line in lines:
            if line.startswith("## ") or line.startswith("用户"):
                summary_lines.append(line)
            if len(summary_lines) >= 4:
                break

        return "\n".join(summary_lines) if summary_lines else "（暂无观察到的行为模式）"

    def _build_sessions_summary(self, recent_sessions: list) -> str:
        """构建会话历史概要"""
        if not recent_sessions:
            return "（暂无历史会话）"

        lines = ["最近 5 次会话："]
        for session in recent_sessions:
            created_at = session.created_at.strftime("%Y-%m-%d")
            summary_short = session.summary[:50] if len(session.summary) > 50 else session.summary
            lines.append(f"- {created_at} | {summary_short}")

        return "\n".join(lines)


def get_memory_service() -> MemoryService:
    """获取 MemoryService 实例"""
    return MemoryService()


__all__ = [
    "MemoryService",
    "get_memory_service",
]