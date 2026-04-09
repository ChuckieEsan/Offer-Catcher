"""缓存服务模块

提供 Redis 缓存的统一管理，包括：
- TTL 随机化（防雪崩）
- 分布式锁（防击穿）
- 缓存空值（防穿透）
- 延迟双删（一致性）
"""

import asyncio
import hashlib
import json
import random
import time
from typing import Any, Callable, List, Optional

from app.db.redis_client import get_redis_client
from app.utils.logger import logger


class CacheKeys:
    """Redis Key 管理器"""

    PREFIX = "oc"
    BASE_TTL = 300  # 5 分钟
    RANDOM_RANGE = 60  # TTL 随机范围 ±1 分钟
    NULL_MARKER = "__NULL__"
    NULL_TTL = 60  # 空值缓存 1 分钟
    LOCK_TTL = 10  # 分布式锁 10 秒

    @classmethod
    def stats_overview(cls) -> str:
        return f"{cls.PREFIX}:stats:overview"

    @classmethod
    def stats_clusters(cls) -> str:
        return f"{cls.PREFIX}:stats:clusters"

    @classmethod
    def stats_companies(cls) -> str:
        return f"{cls.PREFIX}:stats:companies"

    @classmethod
    def questions_list(cls, filter_hash: str) -> str:
        return f"{cls.PREFIX}:questions:list:{filter_hash}"

    @classmethod
    def questions_count(cls, filter_hash: str) -> str:
        return f"{cls.PREFIX}:questions:count:{filter_hash}"

    @classmethod
    def questions_item(cls, question_id: str) -> str:
        return f"{cls.PREFIX}:questions:item:{question_id}"

    @classmethod
    def questions_list_pattern(cls) -> str:
        return f"{cls.PREFIX}:questions:list:*"

    @classmethod
    def questions_count_pattern(cls) -> str:
        return f"{cls.PREFIX}:questions:count:*"

    @classmethod
    def stats_pattern(cls) -> str:
        return f"{cls.PREFIX}:stats:*"

    @classmethod
    def lock_key(cls, key: str) -> str:
        return f"{cls.PREFIX}:lock:{key}"

    @classmethod
    def get_ttl(cls) -> int:
        """获取随机化 TTL，防止缓存雪崩"""
        return cls.BASE_TTL + random.randint(-cls.RANDOM_RANGE, cls.RANDOM_RANGE)


class CacheService:
    """缓存服务

    提供 Redis 缓存的统一管理，包括：
    - TTL 随机化（防雪崩）
    - 分布式锁（防击穿）
    - 缓存空值（防穿透）
    - 延迟双删（一致性）
    """

    def __init__(self):
        self._redis = None

    @property
    def redis(self):
        """获取 Redis 客户端"""
        if self._redis is None:
            self._redis = get_redis_client().client
        return self._redis

    def _hash_params(self, params: Optional[dict]) -> str:
        """生成过滤参数的哈希值

        Args:
            params: 过滤参数字典，可能为 None

        Returns:
            哈希值（8 字符）或 'all'
        """
        if not params:
            return "all"
        # 过滤 None 值并排序
        sorted_items = sorted((k, v) for k, v in params.items() if v is not None)
        if not sorted_items:
            return "all"
        params_str = json.dumps(sorted_items, ensure_ascii=False)
        return hashlib.md5(params_str.encode()).hexdigest()[:8]

    # ========== 基础操作 ==========

    def get(self, key: str) -> tuple[bool, Optional[Any]]:
        """获取缓存值

        Returns:
            tuple[hit, value]:
                - hit=True, value=None: 缓存命中空值标记
                - hit=True, value=data: 缓存命中正常值
                - hit=False, value=None: 缓存不存在
        """
        try:
            value = self.redis.get(key)
            if value is None:
                # 缓存不存在
                return (False, None)
            if value == CacheKeys.NULL_MARKER:
                # 缓存命中空值标记
                return (True, None)
            # 缓存命中正常值
            return (True, json.loads(value))
        except Exception as e:
            logger.warning(f"Redis get failed: {key}, error: {e}")
            return (False, None)

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值

        支持序列化 Pydantic 模型和普通 Python 对象。
        """
        try:
            if value is None:
                # 缓存空值
                self.redis.setex(key, CacheKeys.NULL_TTL, CacheKeys.NULL_MARKER)
            else:
                # 处理 Pydantic 模型序列化
                if hasattr(value, "model_dump"):
                    # 单个 Pydantic 模型，使用 mode='json' 处理 datetime 等
                    serialized = json.dumps(value.model_dump(mode='json'))
                elif isinstance(value, list) and len(value) > 0 and hasattr(value[0], "model_dump"):
                    # Pydantic 模型列表
                    serialized = json.dumps([item.model_dump(mode='json') for item in value])
                else:
                    # 普通对象
                    serialized = json.dumps(value)
                self.redis.setex(key, ttl or CacheKeys.get_ttl(), serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis set failed: {key}, error: {e}")
            return False

    def delete(self, *keys: str) -> bool:
        """删除缓存"""
        try:
            if keys:
                self.redis.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"Redis delete failed: {keys}, error: {e}")
            return False

    def delete_pattern(self, pattern: str) -> bool:
        """删除匹配模式的所有 key

        注意：使用 Redis KEYS 命令，大规模 key 场景下可能阻塞。
        生产环境如需优化，可改用 SCAN 命令（异步迭代）。

        Args:
            pattern: Redis 匹配模式（如 'oc:questions:list:*'）

        Returns:
            True 表示成功，False 表示失败
        """
        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.debug(f"Deleted {len(keys)} keys matching: {pattern}")
            return True
        except Exception as e:
            logger.warning(f"Redis delete_pattern failed: {pattern}, error: {e}")
            return False

    # ========== 分布式锁（防击穿） ==========

    # Lua 脚本：安全释放锁（只有持有锁的线程才能释放）
    _RELEASE_LOCK_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def _acquire_lock(self, key: str) -> str | None:
        """获取分布式锁

        使用 Redis SET 命令的 NX 选项实现分布式锁。

        Returns:
            锁的唯一标识符（用于安全释放），None 表示获取失败
        """
        lock_key = CacheKeys.lock_key(key)
        # 使用 UUID 作为锁的唯一标识
        lock_value = hashlib.md5(f"{key}:{time.time()}:{random.random()}".encode()).hexdigest()
        try:
            # redis-py: set(name, value, ex=None, nx=False)
            # nx=True 表示仅当 key 不存在时才设置
            # 返回 True 表示成功，None/False 表示失败
            result = self.redis.set(lock_key, lock_value, ex=CacheKeys.LOCK_TTL, nx=True)
            if result:
                return lock_value
            return None
        except Exception as e:
            logger.warning(f"Acquire lock failed: {lock_key}, error: {e}")
            return None

    def _release_lock(self, key: str, lock_value: str) -> bool:
        """安全释放分布式锁

        使用 Lua 脚本确保只有持有锁的线程才能释放。
        解决锁误释放问题：防止释放其他线程的锁。

        Args:
            key: 原始缓存 key
            lock_value: 获取锁时返回的唯一标识符

        Returns:
            True 表示成功释放，False 表示锁不存在或不属于当前线程
        """
        lock_key = CacheKeys.lock_key(key)
        try:
            # 使用 Lua 脚本原子性地检查并删除锁
            result = self.redis.eval(
                self._RELEASE_LOCK_SCRIPT,
                1,  # KEYS 数量
                lock_key,  # KEYS[1]
                lock_value,  # ARGV[1]
            )
            return bool(result)
        except Exception as e:
            logger.warning(f"Release lock failed: {lock_key}, error: {e}")
            return False

    def get_with_lock(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        ttl: int = None,
        max_retries: int = 10,
    ) -> Any:
        """带分布式锁的缓存读取（防击穿）

        Args:
            key: 缓存 key
            fetch_fn: 数据获取函数
            ttl: 缓存过期时间
            max_retries: 最大重试次数（默认 10 次，总计等待约 1 秒）

        Returns:
            缓存数据或数据库查询结果
        """
        # 1. 查缓存
        hit, cached = self.get(key)
        if hit:
            # 缓存命中（包括空值标记），直接返回
            return cached

        # 2. 尝试获取锁
        for attempt in range(max_retries):
            lock_value = self._acquire_lock(key)
            if lock_value:
                try:
                    # 3. 双重检查
                    hit, cached = self.get(key)
                    if hit:
                        return cached

                    # 4. 查数据库
                    data = fetch_fn()

                    # 5. 写缓存（包括空值）
                    self.set(key, data, ttl)
                    return data
                finally:
                    # 6. 安全释放锁（使用 Lua 脚本）
                    self._release_lock(key, lock_value)
            else:
                # 7. 等待锁释放（指数退避）
                wait_time = min(0.1 * (2 ** attempt), 1.0)  # 最大等待 1 秒
                time.sleep(wait_time)

        # 8. 锁获取失败，直接查数据库（降级）
        logger.warning(f"Lock acquisition failed after {max_retries} retries: {key}")
        return fetch_fn()

    # ========== 业务方法 ==========

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

        return self.get_with_lock(key, fetch_fn)

    def get_questions_count(
        self,
        filter_params: dict,
        fetch_fn: Callable[[], int],
    ) -> int:
        """获取题目数量（带缓存）"""
        filter_hash = self._hash_params(filter_params)
        key = CacheKeys.questions_count(filter_hash)

        return self.get_with_lock(key, fetch_fn)

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
        return self.get_with_lock(key, fetch_fn)

    def get_stats(self, key: str, fetch_fn: Callable[[], Any]) -> Any:
        """获取统计数据（带缓存）"""
        return self.get_with_lock(key, fetch_fn)

    # ========== 失效操作 ==========

    def invalidate_question(self, question_id: str = None):
        """失效题目相关缓存

        写操作后调用，确保缓存一致性。
        API 和 Worker 都调用此方法。
        """
        try:
            # 1. 删除题目列表缓存（所有过滤组合）
            self.delete_pattern(CacheKeys.questions_list_pattern())
            self.delete_pattern(CacheKeys.questions_count_pattern())

            # 2. 删除统计数据缓存
            self.delete(
                CacheKeys.stats_overview(),
                CacheKeys.stats_clusters(),
                CacheKeys.stats_companies(),
            )

            # 3. 删除单个题目缓存
            if question_id:
                self.delete(CacheKeys.questions_item(question_id))

            logger.info(f"Cache invalidated for question: {question_id}")

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
            # TTL 兜底，无需重试

    async def invalidate_question_delayed(self, question_id: str = None):
        """延迟双删

        解决并发读写问题：
        1. 先删缓存
        2. 写数据库
        3. 延迟 1 秒
        4. 再次删缓存
        """
        # 第一次删除
        self.invalidate_question(question_id)

        # 延迟 1 秒
        await asyncio.sleep(1)

        # 第二次删除
        self.invalidate_question(question_id)


# 全局单例
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """获取缓存服务单例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


__all__ = ["CacheService", "CacheKeys", "get_cache_service"]