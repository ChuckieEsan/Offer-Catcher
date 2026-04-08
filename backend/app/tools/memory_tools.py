"""长期记忆读写工具

提供用户画像、偏好设置、学习进度的读写能力。
使用 ToolRuntime 注入 user_id，支持多用户场景。
"""

from typing import Optional

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from app.memory.long_term import (
    get_long_term_memory,
    UserProfile,
    UserPreferences,
    LearningProgress,
)
from app.tools.context import UserContext


@tool
def save_user_preferences(
    language: Optional[str] = Field(default=None, description="语言偏好：zh/en"),
    difficulty: Optional[str] = Field(default=None, description="难度偏好：easy/medium/hard"),
    practice_batch_size: Optional[int] = Field(default=None, description="单次练习题目数量"),
    show_answer_immediately: Optional[bool] = Field(default=None, description="是否立即显示答案"),
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """保存用户偏好设置。当用户明确说'记住我喜欢...'或'设置难度为...'时使用。

    Args:
        language: 语言偏好，zh 表示中文，en 表示英文
        difficulty: 难度偏好，easy/medium/hard
        practice_batch_size: 单次练习题目数量
        show_answer_immediately: 是否立即显示答案
        runtime: 运行时上下文（自动注入）

    Returns:
        操作结果消息
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()

        # 先读取现有偏好
        existing = memory.get_preferences(user_id)

        # 更新字段
        prefs = UserPreferences(
            language=language or (existing.language if existing else "zh"),
            difficulty=difficulty or (existing.difficulty if existing else "medium"),
            practice_batch_size=practice_batch_size or (existing.practice_batch_size if existing else 5),
            show_answer_immediately=show_answer_immediately if show_answer_immediately is not None else (existing.show_answer_immediately if existing else False),
        )

        memory.save_preferences(user_id, prefs)

        result_parts = []
        if language:
            result_parts.append(f"语言={language}")
        if difficulty:
            result_parts.append(f"难度={difficulty}")
        if practice_batch_size:
            result_parts.append(f"单次练习={practice_batch_size} 道")

        return f"已保存偏好设置：{', '.join(result_parts) if result_parts else '无变化'}"
    except Exception as e:
        return f"保存偏好失败：{e}"


@tool
def save_user_profile(
    preferred_companies: Optional[list[str]] = Field(default=None, description="目标公司列表"),
    target_position: Optional[str] = Field(default=None, description="目标岗位"),
    tech_stack: Optional[list[str]] = Field(default=None, description="技术栈列表"),
    experience_years: Optional[int] = Field(default=None, description="工作年限"),
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """保存用户画像。当用户提到'我想去 XX 公司'或'我是 XX 开发'时使用。

    Args:
        preferred_companies: 目标公司列表
        target_position: 目标岗位
        tech_stack: 技术栈列表
        experience_years: 工作年限
        runtime: 运行时上下文（自动注入）

    Returns:
        操作结果消息
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()

        existing = memory.get_profile(user_id)

        profile = UserProfile(
            user_id=user_id,
            preferred_companies=preferred_companies or (existing.preferred_companies if existing else []),
            target_position=target_position or (existing.target_position if existing else ""),
            tech_stack=tech_stack or (existing.tech_stack if existing else []),
            experience_years=experience_years or (existing.experience_years if existing else None),
        )

        memory.save_profile(user_id, profile)

        result_parts = []
        if preferred_companies:
            result_parts.append(f"目标公司={preferred_companies}")
        if target_position:
            result_parts.append(f"岗位={target_position}")
        if tech_stack:
            result_parts.append(f"技术栈={tech_stack}")

        return f"已更新用户画像：{', '.join(result_parts) if result_parts else '无变化'}"
    except Exception as e:
        return f"保存画像失败：{e}"


@tool
def update_learning_progress(
    mastered_entities: Optional[list[str]] = Field(default=None, description="新掌握的知识点"),
    completed_question_ids: Optional[list[str]] = Field(default=None, description="已完成的题目 ID"),
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """更新学习进度。当用户完成练习或标记知识点为'已掌握'时使用。

    Args:
        mastered_entities: 新掌握的知识点列表
        completed_question_ids: 已完成的题目 ID 列表
        runtime: 运行时上下文（自动注入）

    Returns:
        操作结果消息
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()

        existing = memory.get_progress(user_id)

        # 合并已掌握的知识点（去重）
        existing_entities = existing.mastered_entities if existing else []
        new_entities = mastered_entities or []
        all_entities = list(set(existing_entities + new_entities))

        # 累加答题数量
        existing_count = existing.total_questions_answered if existing else 0
        new_count = len(completed_question_ids or [])

        progress = LearningProgress(
            mastered_entities=all_entities,
            pending_review_question_ids=existing.pending_review_question_ids if existing else [],
            total_questions_answered=existing_count + new_count,
            last_review_date=existing.last_review_date if existing else None,
        )

        memory.save_progress(user_id, progress)

        return (
            f"已更新学习进度："
            f"已掌握知识点={len(all_entities)} 个，"
            f"累计答题={progress.total_questions_answered} 道"
        )
    except Exception as e:
        return f"更新进度失败：{e}"


@tool
def get_user_preferences(
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """获取用户偏好设置。当用户询问'我的设置是什么'时使用。

    Args:
        runtime: 运行时上下文（自动注入）

    Returns:
        用户偏好设置的文本描述
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()
        prefs = memory.get_preferences(user_id)

        if not prefs:
            return "暂无用户偏好设置"

        return (
            f"当前偏好设置：\\n"
            f"- 语言：{'中文' if prefs.language == 'zh' else 'English'}\\n"
            f"- 难度：{prefs.difficulty}\\n"
            f"- 单次练习：{prefs.practice_batch_size} 道题\\n"
            f"- 立即显示答案：{'是' if prefs.show_answer_immediately else '否'}"
        )
    except Exception as e:
        return f"获取偏好失败：{e}"


@tool
def get_user_profile(
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """获取用户画像。当用户询问'我的目标是什么'或'我记录了什么公司'时使用。

    Args:
        runtime: 运行时上下文（自动注入）

    Returns:
        用户画像的文本描述
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()
        profile = memory.get_profile(user_id)

        if not profile:
            return "暂无用户画像"

        lines = ["当前画像："]
        if profile.preferred_companies:
            lines.append(f"- 目标公司：{', '.join(profile.preferred_companies)}")
        if profile.target_position:
            lines.append(f"- 目标岗位：{profile.target_position}")
        if profile.tech_stack:
            lines.append(f"- 技术栈：{', '.join(profile.tech_stack)}")
        if profile.experience_years:
            lines.append(f"- 工作年限：{profile.experience_years} 年")

        return "\\n".join(lines)
    except Exception as e:
        return f"获取画像失败：{e}"


@tool
def get_learning_progress(
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """获取学习进度。当用户询问'我的学习进度如何'时使用。

    Args:
        runtime: 运行时上下文（自动注入）

    Returns:
        学习进度的文本描述
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()
        progress = memory.get_progress(user_id)

        if not progress:
            return "暂无学习进度记录"

        return (
            f"学习进度：\\n"
            f"- 已掌握知识点：{len(progress.mastered_entities)} 个\\n"
            f"- 待复习题目：{len(progress.pending_review_question_ids)} 道\\n"
            f"- 累计答题：{progress.total_questions_answered} 道"
        )
    except Exception as e:
        return f"获取进度失败：{e}"


@tool
def clear_user_memory(
    runtime: ToolRuntime[UserContext] = None,
) -> str:
    """清除用户记忆数据。当用户明确要求'清除我的所有数据'时使用。

    Args:
        runtime: 运行时上下文（自动注入）

    Returns:
        操作结果消息
    """
    user_id = runtime.context.user_id
    try:
        memory = get_long_term_memory()

        # 清空画像
        memory.save_profile(user_id, UserProfile(user_id=user_id))

        # 清空偏好
        memory.save_preferences(user_id, UserPreferences())

        # 清空进度
        memory.save_progress(user_id, LearningProgress())

        return "已清除所有用户记忆数据"
    except Exception as e:
        return f"清除记忆失败：{e}"


__all__ = [
    "save_user_preferences",
    "save_user_profile",
    "update_learning_progress",
    "get_user_preferences",
    "get_user_profile",
    "get_learning_progress",
    "clear_user_memory",
    "UserContext",
]