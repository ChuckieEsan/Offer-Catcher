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

    def _make_key(self, user_id: str, conversation_id: str) -> str:
        """生成 Redis Key（包含 user_id 多租户隔离）"""
        return f"chat:{user_id}:short_term:{conversation_id}"

    def get_short_term_memory(
        self,
        user_id: str,
        conversation_id: str,
    ) -> Optional[dict]:
        """获取短期记忆

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            短期记忆字典，或 None（不存在）
        """
        key = self._make_key(user_id, conversation_id)
        try:
            data = self._client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get short term memory: {e}")
            return None

    def set_short_term_memory(
        self,
        user_id: str,
        conversation_id: str,
        context: list,
        user_info: Optional[dict] = None,
    ) -> bool:
        """设置短期记忆

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            context: 对话上下文
            user_info: 用户关键信息

        Returns:
            是否成功
        """
        key = self._make_key(user_id, conversation_id)
        value = {
            "context": context,
            "user_info": user_info or {},
        }
        try:
            self._client.setex(key, self._ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.error(f"Failed to set short term memory: {e}")
            return False

    def append_to_context(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> bool:
        """追加消息到短期记忆

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            role: 角色 (user/assistant)
            content: 消息内容

        Returns:
            是否成功
        """
        memory = self.get_short_term_memory(user_id, conversation_id)
        if memory is None:
            memory = {"context": [], "user_info": {}}

        memory["context"].append({
            "role": role,
            "content": content,
        })

        return self.set_short_term_memory(
            user_id=user_id,
            conversation_id=conversation_id,
            context=memory["context"],
            user_info=memory.get("user_info"),
        )

    def delete_short_term_memory(
        self,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        """删除短期记忆

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            是否成功
        """
        key = self._make_key(user_id, conversation_id)
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete short term memory: {e}")
            return False

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