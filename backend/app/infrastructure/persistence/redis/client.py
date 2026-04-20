"""Redis 客户端 - 短期记忆存储

提供 Redis 连接和短期记忆管理功能。
作为基础设施层持久化组件，为应用层提供短期记忆服务。
"""

import json
from typing import Any, Optional

import redis

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class RedisClient:
    """Redis 客户端

    用于短期记忆存储，支持：
    - 对话上下文缓存
    - 用户关键信息存储
    - TTL 自动过期

    设计原则：
    - 多租户隔离（user_id 作为 key 前缀）
    - 连接池复用
    - 自动 TTL 管理
    """

    def __init__(self) -> None:
        """初始化 Redis 客户端"""
        settings = get_settings()
        self._ttl = settings.redis_ttl
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
        logger.info(f"RedisClient connected: {settings.redis_host}:{settings.redis_port}")

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 连接"""
        return self._client

    @property
    def ttl(self) -> int:
        """获取默认 TTL"""
        return self._ttl


    def close(self) -> None:
        """关闭连接"""
        if self._client:
            self._client.close()


# 单例获取函数
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """获取 Redis 客户端单例

    Returns:
        RedisClient 实例
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


__all__ = [
    "RedisClient",
    "get_redis_client",
]