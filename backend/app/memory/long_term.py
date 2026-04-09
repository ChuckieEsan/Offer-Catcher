"""长期记忆模块

使用 LangGraph PostgresStore 实现用户画像、偏好设置、学习进度和会话摘要的持久化存储。

注意：PostgresStore.from_conn_string() 返回上下文管理器，
需要在每次操作时使用 with 语句进入上下文。
"""

from typing import Optional
from datetime import datetime
from contextlib import contextmanager

from pydantic import BaseModel, Field
from langgraph.store.postgres import PostgresStore

from app.config.settings import get_settings
from app.utils.logger import logger
from app.utils.cache import singleton


class UserProfile(BaseModel):
    """用户画像

    Attributes:
        user_id: 用户 ID
        preferred_companies: 目标公司列表
        target_position: 目标岗位
        tech_stack: 技术栈列表
        experience_years: 工作年限
    """
    user_id: str
    preferred_companies: list[str] = Field(default_factory=list)
    target_position: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    experience_years: Optional[int] = None


class UserPreferences(BaseModel):
    """用户偏好设置

    Attributes:
        language: 语言偏好（zh/en）
        difficulty: 难度偏好（easy/medium/hard）
        practice_batch_size: 单次练习题目数量
        show_answer_immediately: 是否立即显示答案
    """
    language: str = "zh"
    difficulty: str = "medium"
    practice_batch_size: int = 5
    show_answer_immediately: bool = False


class LearningProgress(BaseModel):
    """学习进度

    Attributes:
        mastered_entities: 已掌握的知识点列表
        pending_review_question_ids: 待复习的题目 ID 列表
        total_questions_answered: 累计答题数量
        last_review_date: 最后复习日期
    """
    mastered_entities: list[str] = Field(default_factory=list)
    pending_review_question_ids: list[str] = Field(default_factory=list)
    total_questions_answered: int = 0
    last_review_date: Optional[str] = None


class SessionSummary(BaseModel):
    """会话摘要

    Attributes:
        session_id: 会话 ID
        summary: 会话摘要文本
        key_topics: 关键话题列表
        created_at: 创建时间
    """
    session_id: str
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class LongTermMemoryManager:
    """长期记忆管理器

    使用 LangGraph PostgresStore 存储用户相关数据。

    存储结构:
        ("users", user_id, "profile") → UserProfile
        ("users", user_id, "preferences") → UserPreferences
        ("users", user_id, "progress") → LearningProgress
        ("users", user_id, "summaries", session_id) → SessionSummary
    """

    def __init__(self) -> None:
        """初始化长期记忆管理器"""
        self._postgres_url: Optional[str] = None
        self._initialized = False
        self._init_error: Optional[str] = None

    def initialize(self) -> None:
        """初始化 PostgresStore（创建表结构）"""
        try:
            settings = get_settings()
            self._postgres_url = settings.postgres_url

            # 创建表结构
            with PostgresStore.from_conn_string(self._postgres_url) as store:
                store.setup()

            self._initialized = True
            logger.info("LongTermMemory initialized with PostgresStore")
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"LongTermMemory init failed (using fallback): {e}")
            self._initialized = False

    @property
    def initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @contextmanager
    def _get_store(self):
        """获取 PostgresStore 上下文管理器"""
        if not self._initialized or not self._postgres_url:
            raise RuntimeError("LongTermMemory not initialized")
        with PostgresStore.from_conn_string(self._postgres_url) as store:
            yield store

    def _get_namespace(self, user_id: str, category: str) -> tuple:
        """生成命名空间元组"""
        return ("users", user_id, category)

    # ==================== UserProfile ====================

    def save_profile(self, user_id: str, profile: UserProfile) -> None:
        """保存用户画像"""
        if not self._initialized:
            logger.warning("Store not initialized, skipping save_profile")
            return
        try:
            with self._get_store() as store:
                store.put(
                    self._get_namespace(user_id, "profile"),
                    "user_profile",
                    profile.model_dump(),
                )
            logger.info(f"Saved user profile for {user_id}")
        except Exception as e:
            logger.error(f"Failed to save user profile: {e}")

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        if not self._initialized:
            return None
        try:
            with self._get_store() as store:
                result = store.get(
                    self._get_namespace(user_id, "profile"),
                    "user_profile",
                )
                if result and result.value:
                    return UserProfile.model_validate(result.value)
                return None
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return None

    # ==================== UserPreferences ====================

    def save_preferences(self, user_id: str, preferences: UserPreferences) -> None:
        """保存用户偏好设置"""
        if not self._initialized:
            return
        try:
            with self._get_store() as store:
                store.put(
                    self._get_namespace(user_id, "preferences"),
                    "user_preferences",
                    preferences.model_dump(),
                )
            logger.info(f"Saved user preferences for {user_id}")
        except Exception as e:
            logger.error(f"Failed to save user preferences: {e}")

    def get_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """获取用户偏好设置"""
        if not self._initialized:
            return None
        try:
            with self._get_store() as store:
                result = store.get(
                    self._get_namespace(user_id, "preferences"),
                    "user_preferences",
                )
                if result and result.value:
                    return UserPreferences.model_validate(result.value)
                return None
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return None

    # ==================== LearningProgress ====================

    def save_progress(self, user_id: str, progress: LearningProgress) -> None:
        """保存学习进度"""
        if not self._initialized:
            return
        try:
            with self._get_store() as store:
                store.put(
                    self._get_namespace(user_id, "progress"),
                    "learning_progress",
                    progress.model_dump(),
                )
            logger.info(f"Saved learning progress for {user_id}")
        except Exception as e:
            logger.error(f"Failed to save learning progress: {e}")

    def get_progress(self, user_id: str) -> Optional[LearningProgress]:
        """获取学习进度"""
        if not self._initialized:
            return None
        try:
            with self._get_store() as store:
                result = store.get(
                    self._get_namespace(user_id, "progress"),
                    "learning_progress",
                )
                if result and result.value:
                    return LearningProgress.model_validate(result.value)
                return None
        except Exception as e:
            logger.error(f"Failed to get learning progress: {e}")
            return None

    # ==================== SessionSummary ====================

    def save_session_summary(self, user_id: str, summary: SessionSummary) -> None:
        """保存会话摘要"""
        if not self._initialized:
            return
        try:
            with self._get_store() as store:
                store.put(
                    self._get_namespace(user_id, "summaries"),
                    summary.session_id,
                    summary.model_dump(),
                )
            logger.info(f"Saved session summary for {user_id}/{summary.session_id}")
        except Exception as e:
            logger.error(f"Failed to save session summary: {e}")

    def get_session_summary(self, user_id: str, session_id: str) -> Optional[SessionSummary]:
        """获取会话摘要"""
        if not self._initialized:
            return None
        try:
            with self._get_store() as store:
                result = store.get(
                    self._get_namespace(user_id, "summaries"),
                    session_id,
                )
                if result and result.value:
                    return SessionSummary.model_validate(result.value)
                return None
        except Exception as e:
            logger.error(f"Failed to get session summary: {e}")
            return None

    def list_session_summaries(self, user_id: str) -> list[SessionSummary]:
        """列出用户的所有会话摘要"""
        if not self._initialized:
            return []
        try:
            with self._get_store() as store:
                results = store.search(
                    ("users", user_id, "summaries"),
                    limit=100,
                )
                summaries = []
                for r in results:
                    if r.value:
                        summaries.append(SessionSummary.model_validate(r.value))
                return summaries
        except Exception as e:
            logger.error(f"Failed to list session summaries: {e}")
            return []


# ==================== 全局单例 ====================

_memory_manager: Optional[LongTermMemoryManager] = None


@singleton
def get_long_term_memory() -> LongTermMemoryManager:
    """获取长期记忆管理器单例"""
    manager = LongTermMemoryManager()
    manager.initialize()
    return manager


def get_user_context_prompt(user_id: str) -> str:
    """获取用户上下文 Prompt（用于注入到 System Prompt）

    Args:
        user_id: 用户 ID

    Returns:
        用户上下文 Prompt 文本
    """
    memory = get_long_term_memory()
    lines = ["<user_context>"]

    # 用户画像
    profile = memory.get_profile(user_id)
    if profile:
        lines.append(f"- 目标公司：{', '.join(profile.preferred_companies) or '未设置'}")
        lines.append(f"- 目标岗位：{profile.target_position or '未设置'}")
        lines.append(f"- 技术栈：{', '.join(profile.tech_stack) or '未设置'}")

    # 偏好设置
    prefs = memory.get_preferences(user_id)
    if prefs:
        lang = "中文" if prefs.language == "zh" else "English"
        lines.append(f"- 语言偏好：{lang}")
        lines.append(f"- 难度偏好：{prefs.difficulty}")
        lines.append(f"- 单次练习：{prefs.practice_batch_size} 道题")

    # 学习进度
    progress = memory.get_progress(user_id)
    if progress:
        lines.append(f"- 已掌握知识点：{len(progress.mastered_entities)} 个")
        lines.append(f"- 待复习题目：{len(progress.pending_review_question_ids)} 道")
        lines.append(f"- 累计答题：{progress.total_questions_answered} 道")

    lines.append("</user_context>")
    return "\n".join(lines)


__all__ = [
    "UserProfile",
    "UserPreferences",
    "LearningProgress",
    "SessionSummary",
    "LongTermMemoryManager",
    "get_long_term_memory",
    "get_user_context_prompt",
]