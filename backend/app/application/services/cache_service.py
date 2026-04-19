"""缓存应用服务

编排缓存用例，包含业务决策逻辑：
- 缓存失效决策（哪些缓存需要失效）
- 延迟双删（一致性策略）

依赖 CacheAdapter 提供基础缓存能力。
依赖 CacheKeys（Infrastructure 层）提供 key 命名规则。
"""

import asyncio
import hashlib
import json
from typing import Any, Callable, List, Optional

from pydantic import BaseModel

from app.infrastructure.adapters.cache_adapter import (
    CacheAdapter,
    get_cache_adapter,
)
from app.infrastructure.common.cache import singleton
from app.infrastructure.common.cache_keys import CacheKeys
from app.infrastructure.common.logger import logger


class CacheApplicationService:
    """缓存应用服务

    编排缓存用例，包含业务决策：
    - 何时使用缓存
    - 哪些缓存需要失效
    - 缓存一致性策略

    依赖 CacheAdapter 提供基础技术能力。
    """

    def __init__(self, adapter: Optional[CacheAdapter] = None) -> None:
        """初始化缓存应用服务

        Args:
            adapter: 缓存适配器（支持依赖注入）
        """
        self._adapter = adapter or get_cache_adapter()

    def _hash_params(self, params: Optional[dict]) -> str:
        """生成过滤参数的哈希值

        Args:
            params: 过滤参数字典

        Returns:
            哈希值或 'all'
        """
        if not params:
            return "all"
        sorted_items = sorted((k, v) for k, v in params.items() if v is not None)
        if not sorted_items:
            return "all"
        params_str = json.dumps(sorted_items, ensure_ascii=False)
        return hashlib.md5(params_str.encode()).hexdigest()[:8]

    # ========== 业务缓存方法 ==========

    def get_with_lock(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        ttl: int = None,
    ) -> Any:
        """带锁读取缓存

        Args:
            key: 缓存 key
            fetch_fn: 数据获取函数
            ttl: 缓存过期时间

        Returns:
            缓存数据或数据库查询结果
        """
        return self._adapter.get_with_lock(key, fetch_fn, ttl)

    def get_questions_list(
        self,
        filter_params: dict,
        fetch_fn: Callable[[], List],
    ) -> List:
        """获取题目列表（带缓存）

        Args:
            filter_params: 过滤参数
            fetch_fn: 数据获取函数

        Returns:
            题目列表
        """
        filter_hash = self._hash_params(filter_params)
        key = CacheKeys.questions_list(filter_hash)
        return self._adapter.get_with_lock(key, fetch_fn)

    def get_questions_count(
        self,
        filter_params: dict,
        fetch_fn: Callable[[], int],
    ) -> int:
        """获取题目数量（带缓存）"""
        filter_hash = self._hash_params(filter_params)
        key = CacheKeys.questions_count(filter_hash)
        return self._adapter.get_with_lock(key, fetch_fn)

    def get_question_item(
        self,
        question_id: str,
        fetch_fn: Callable[[], Any],
    ) -> Any:
        """获取单个题目（带缓存，防穿透）

        Args:
            question_id: 题目 ID
            fetch_fn: 数据获取函数

        Returns:
            题目数据或 None
        """
        key = CacheKeys.questions_item(question_id)
        return self._adapter.get_with_lock(key, fetch_fn)

    def get_stats(self, key: str, fetch_fn: Callable[[], Any]) -> Any:
        """获取统计数据（带缓存）"""
        return self._adapter.get_with_lock(key, fetch_fn)

    # ========== 缓存失效（业务决策） ==========

    def invalidate_question(self, question_id: str = None) -> None:
        """失效题目相关缓存

        业务决策：题目变化后，哪些缓存需要失效？
        - 题目列表缓存（所有过滤组合）
        - 统计数据缓存
        - 单个题目缓存
        - 工具缓存（搜索结果可能变化）

        Args:
            question_id: 题目 ID（可选）
        """
        try:
            # 1. 删除题目列表缓存
            self._adapter.delete_pattern(CacheKeys.questions_list_pattern())
            self._adapter.delete_pattern(CacheKeys.questions_count_pattern())

            # 2. 删除统计数据缓存
            self._adapter.delete_pattern(CacheKeys.stats_entities_pattern())
            self._adapter.delete(
                CacheKeys.stats_overview(),
                CacheKeys.stats_clusters(),
                CacheKeys.stats_companies(),
            )

            # 3. 删除单个题目缓存
            if question_id:
                self._adapter.delete(CacheKeys.questions_item(question_id))

            # 4. 删除工具缓存
            self._adapter.delete_pattern(CacheKeys.tool_search_pattern())

            logger.info(f"Cache invalidated for question: {question_id}")

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    def invalidate_tools_cache(self) -> None:
        """失效所有工具缓存

        用于数据更新后清除工具层的缓存。
        """
        try:
            self._adapter.delete_pattern(CacheKeys.tool_search_pattern())
            self._adapter.delete_pattern(CacheKeys.tool_graph_pattern())
            logger.info("Tools cache invalidated")
        except Exception as e:
            logger.warning(f"Tools cache invalidation failed: {e}")

    async def invalidate_question_delayed(self, question_id: str = None) -> None:
        """延迟双删

        解决并发读写问题：
        1. 先删缓存
        2. 写数据库
        3. 延迟 1 秒
        4. 再次删缓存

        Args:
            question_id: 题目 ID
        """
        self.invalidate_question(question_id)
        await asyncio.sleep(1)
        self.invalidate_question(question_id)


# 单例获取函数
@singleton
def get_cache_service() -> CacheApplicationService:
    """获取缓存应用服务单例"""
    return CacheApplicationService()


__all__ = [
    "CacheApplicationService",
    "get_cache_service",
]