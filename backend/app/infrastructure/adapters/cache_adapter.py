"""缓存适配器

提供 Redis 缓存的基础技术能力，包括：
- get/set/delete/delete_pattern 基础操作
- 分布式锁（防击穿）
- 空值标记（防穿透）
- TTL 随机化（防雪崩）

作为基础设施层适配器，不包含业务逻辑。
"""

import hashlib
import json
import random
import time
from typing import Any, Callable, Optional

from app.infrastructure.persistence.redis import get_redis_client
from app.infrastructure.common.cache import singleton
from app.infrastructure.common.logger import logger


class CacheAdapter:
    """缓存适配器

    提供 Redis 缓存的基础技术能力。
    不包含业务逻辑，仅提供技术实现。

    设计原则：
    - TTL 随机化（防雪崩）
    - 分布式锁（防击穿）
    - 空值标记（防穿透）
    - 支持依赖注入便于测试
    """

    # 缓存配置常量
    PREFIX = "oc"
    BASE_TTL = 300  # 5 分钟
    RANDOM_RANGE = 60  # TTL 随机范围 ±1 分钟
    NULL_MARKER = "__NULL__"
    NULL_TTL = 60  # 空值缓存 1 分钟
    LOCK_TTL = 10  # 分布式锁 10 秒

    # Lua 脚本：安全释放锁
    _RELEASE_LOCK_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self) -> None:
        """初始化缓存适配器"""
        self._redis = None

    @property
    def redis(self):
        """获取 Redis 客户端"""
        if self._redis is None:
            self._redis = get_redis_client().client
        return self._redis

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
                return (False, None)
            if value == self.NULL_MARKER:
                return (True, None)
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
                self.redis.setex(key, self.NULL_TTL, self.NULL_MARKER)
            else:
                if hasattr(value, "model_dump"):
                    serialized = json.dumps(value.model_dump(mode='json'))
                elif isinstance(value, list) and len(value) > 0 and hasattr(value[0], "model_dump"):
                    serialized = json.dumps([item.model_dump(mode='json') for item in value])
                else:
                    serialized = json.dumps(value)
                self.redis.setex(key, ttl or self.get_random_ttl(), serialized)
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

        Args:
            pattern: Redis 匹配模式

        Returns:
            是否成功
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

    # ========== TTL 随机化 ==========

    def get_random_ttl(self) -> int:
        """获取随机化 TTL，防止缓存雪崩"""
        return self.BASE_TTL + random.randint(-self.RANDOM_RANGE, self.RANDOM_RANGE)

    # ========== 分布式锁 ==========

    def lock_key(self, key: str) -> str:
        """生成锁 key"""
        return f"{self.PREFIX}:lock:{key}"

    def acquire_lock(self, key: str) -> str | None:
        """获取分布式锁

        Returns:
            锁的唯一标识符，None 表示获取失败
        """
        lock_key = self.lock_key(key)
        lock_value = hashlib.md5(f"{key}:{time.time()}:{random.random()}".encode()).hexdigest()
        try:
            result = self.redis.set(lock_key, lock_value, ex=self.LOCK_TTL, nx=True)
            if result:
                return lock_value
            return None
        except Exception as e:
            logger.warning(f"Acquire lock failed: {lock_key}, error: {e}")
            return None

    def release_lock(self, key: str, lock_value: str) -> bool:
        """安全释放分布式锁

        Args:
            key: 原始缓存 key
            lock_value: 获取锁时返回的唯一标识符

        Returns:
            是否成功释放
        """
        lock_key = self.lock_key(key)
        try:
            result = self.redis.eval(
                self._RELEASE_LOCK_SCRIPT,
                1,
                lock_key,
                lock_value,
            )
            return bool(result)
        except Exception as e:
            logger.warning(f"Release lock failed: {lock_key}, error: {e}")
            return False

    # ========== 带锁读取 ==========

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
            max_retries: 最大重试次数

        Returns:
            缓存数据或数据库查询结果
        """
        # 1. 查缓存
        hit, cached = self.get(key)
        if hit:
            return cached

        # 2. 尝试获取锁
        for attempt in range(max_retries):
            lock_value = self.acquire_lock(key)
            if lock_value:
                try:
                    # 3. 双重检查
                    hit, cached = self.get(key)
                    if hit:
                        return cached

                    # 4. 查数据库
                    data = fetch_fn()

                    # 5. 写缓存
                    self.set(key, data, ttl)
                    return data
                finally:
                    # 6. 安全释放锁
                    self.release_lock(key, lock_value)
            else:
                # 7. 等待锁释放（指数退避）
                wait_time = min(0.1 * (2 ** attempt), 1.0)
                time.sleep(wait_time)

        # 8. 锁获取失败，直接查数据库（降级）
        logger.warning(f"Lock acquisition failed after {max_retries} retries: {key}")
        return fetch_fn()


# 单例获取函数
@singleton
def get_cache_adapter() -> CacheAdapter:
    """获取缓存适配器单例"""
    return CacheAdapter()


__all__ = [
    "CacheAdapter",
    "get_cache_adapter",
]