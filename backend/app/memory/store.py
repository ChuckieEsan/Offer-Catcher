"""PostgresStore 存储初始化

使用 LangGraph PostgresStore 实现记忆文件的持久化存储。

命名空间结构（LangGraph PostgresStore 不允许命名空间标签包含点号）：
    ("memory", user_id) → MEMORY（对应 MEMORY.md）
    ("memory", user_id, "references", "preferences") → preferences（对应 preferences.md）
    ("memory", user_id, "references", "behaviors") → behaviors（对应 behaviors.md）
    ("memory", user_id, "references", "skills", skill_name, "SKILL") → SKILL（对应 SKILL.md）
"""

from typing import Optional
from contextlib import contextmanager

from langgraph.store.postgres import PostgresStore

from app.infrastructure.config.settings import get_settings
from app.utils.logger import logger
from app.utils.cache import singleton


class MemoryStore:
    """记忆存储管理器

    使用 LangGraph PostgresStore 存储用户记忆文件。

    注意：PostgresStore.from_conn_string() 返回上下文管理器，
    需要在每次操作时使用 with 语句进入上下文。
    """

    def __init__(self) -> None:
        """初始化记忆存储管理器"""
        self._postgres_url: Optional[str] = None
        self._initialized: bool = False
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
            logger.info("MemoryStore initialized with PostgresStore")
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"MemoryStore init failed: {e}")
            self._initialized = False

    @property
    def initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def init_error(self) -> Optional[str]:
        """初始化错误信息"""
        return self._init_error

    @contextmanager
    def _get_store(self):
        """获取 PostgresStore 上下文管理器

        Yields:
            PostgresStore 实例

        Raises:
            RuntimeError: 存储未初始化
        """
        if not self._initialized or not self._postgres_url:
            raise RuntimeError("MemoryStore not initialized")
        with PostgresStore.from_conn_string(self._postgres_url) as store:
            yield store


# ==================== 全局单例 ====================


@singleton
def get_memory_store() -> MemoryStore:
    """获取记忆存储管理器单例

    Returns:
        MemoryStore 实例
    """
    store = MemoryStore()
    store.initialize()
    return store


__all__ = [
    "MemoryStore",
    "get_memory_store",
]