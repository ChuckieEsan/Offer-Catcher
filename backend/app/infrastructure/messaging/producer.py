"""RabbitMQ 异步消息生产者模块

基于 aio-pika 提供消息发布功能，用于将需要异步生成答案的题目发送到队列。
作为基础设施层消息组件，为应用层提供消息发布服务。
"""

import asyncio
from typing import Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel
from aio_pika import Message, DeliveryMode

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger
from app.models import MQTaskMessage


class RabbitMQProducer:
    """基于 aio-pika 的异步消息生产者

    提供以下核心功能：
    - 建立与 RabbitMQ 的强健连接（自动处理断线重连）
    - 发布单条或批量任务消息
    - 可靠的消息发布（带重试机制）

    设计原则：
    - 连接池管理
    - 自动重连
    - 支持依赖注入
    """

    def __init__(self) -> None:
        """初始化生产者"""
        settings = get_settings()
        self._host = settings.rabbitmq_host
        self._port = settings.rabbitmq_port
        self._user = settings.rabbitmq_user
        self._password = settings.rabbitmq_password
        self._queue = settings.rabbitmq_queue
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractRobustChannel] = None
        self._exchange = None

    async def connect(self) -> bool:
        """建立与 RabbitMQ 的强健连接"""
        try:
            self._connection = await aio_pika.connect_robust(
                host=self._host,
                port=self._port,
                login=self._user,
                password=self._password,
            )
            self._channel = await self._connection.channel()

            await self._channel.declare_queue(self._queue, durable=True)
            self._exchange = self._channel.default_exchange

            logger.info(f"RabbitMQProducer connected: {self._host}:{self._port}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect RabbitMQ: {e}")
            raise

    async def _ensure_connected(self) -> None:
        """确保连接有效，如果连接已关闭则自动重连"""
        if self._connection is None:
            logger.warning("RabbitMQ producer not connected, connecting...")
            await self.connect()
            return

        try:
            if self._connection.is_closed:
                logger.warning("RabbitMQ producer connection closed, reconnecting...")
                await self.connect()
        except RuntimeError as e:
            if "event loop" in str(e).lower():
                logger.warning(f"Event loop issue: {e}, recreating connection...")
                self._connection = None
                self._channel = None
                await self.connect()
            else:
                raise

    async def publish_task(self, task: MQTaskMessage, retry: int = 3) -> bool:
        """发布单条任务消息

        Args:
            task: 任务消息
            retry: 发布失败时的重试次数

        Returns:
            是否发布成功
        """
        await self._ensure_connected()

        for attempt in range(retry):
            try:
                body = task.model_dump_json()

                msg = Message(
                    body=body.encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    message_id=task.question_id,
                )

                await self._exchange.publish(msg, routing_key=self._queue)

                logger.info(f"Published task: question_id={task.question_id}, company={task.company}")
                return True

            except Exception as e:
                logger.warning(f"Publish attempt {attempt + 1}/{retry} failed: {e}. Reconnecting...")
                await self.connect()

        logger.error(f"Failed to publish task after {retry} attempts")
        return False

    async def publish_tasks(self, tasks: list[MQTaskMessage]) -> int:
        """批量发布任务消息

        Args:
            tasks: 任务消息列表

        Returns:
            成功发布的数量
        """
        success_count = 0
        for task in tasks:
            if await self.publish_task(task):
                success_count += 1

        logger.info(f"Published {success_count}/{len(tasks)} tasks")
        return success_count

    async def close(self, cleanup: bool = False) -> None:
        """关闭连接

        Args:
            cleanup: 如果为 True，则关闭连接并重置单例
        """
        try:
            if self._connection is None:
                return

            if not self._connection.is_closed:
                await self._connection.close()
                logger.info("RabbitMQ producer connection closed")
        except RuntimeError as e:
            if "event loop" in str(e).lower():
                logger.warning(f"Cannot close connection: {e}")
            else:
                logger.warning(f"Error closing connection: {e}")
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
        finally:
            self._connection = None
            self._channel = None
            if cleanup:
                _reset_producer()


# 全局单例实例和锁
_producer_instance: Optional[RabbitMQProducer] = None
_producer_lock = None


def _get_lock():
    """获取异步锁（延迟初始化）"""
    global _producer_lock
    if _producer_lock is None:
        _producer_lock = asyncio.Lock()
    return _producer_lock


def _reset_producer() -> None:
    """重置生产者单例"""
    global _producer_instance
    _producer_instance = None


async def get_producer() -> RabbitMQProducer:
    """获取异步生产者单例

    Returns:
        RabbitMQProducer 实例
    """
    global _producer_instance

    if _producer_instance is not None:
        if _producer_instance._connection is not None and not _producer_instance._connection.is_closed:
            return _producer_instance

    async with _get_lock():
        if _producer_instance is not None:
            if _producer_instance._connection is not None and not _producer_instance._connection.is_closed:
                return _producer_instance

        _producer_instance = RabbitMQProducer()
        await _producer_instance.connect()
        return _producer_instance


# 向后兼容的别名
AsyncRabbitMQProducer = RabbitMQProducer


__all__ = [
    "RabbitMQProducer",
    "get_producer",
    "AsyncRabbitMQProducer",
]