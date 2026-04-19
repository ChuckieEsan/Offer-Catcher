"""RabbitMQ 异步消息消费者模块

基于 aio-pika 提供高并发的协程消息消费功能。
支持断路器与降级机制（重新入队与死信队列 DLQ）。
作为基础设施层消息组件，为应用层提供消息消费服务。
"""

import asyncio
import json
import time
from typing import Callable, Awaitable, Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger
from app.infrastructure.messaging.message_helper import get_mq_message_helper
from app.infrastructure.messaging.messages import MQTaskMessage
from app.infrastructure.common.circuit_breaker import create_circuit_breaker, CircuitOpenState


# 创建消费者专用的断路器
_message_breaker = create_circuit_breaker(
    fail_max=5,
    timeout_duration=30.0,
    name="rabbitmq_consumer",
)


class RabbitMQConsumer:
    """基于 aio-pika 的异步消息消费者

    提供以下核心功能：
    - 建立与 RabbitMQ 的强健连接（自动处理断线重连）
    - 启动并发消费协程
    - 支持手动 ACK/Nack
    - 可设置 prefetch_count 控制并发
    - 熔断与降级机制

    设计原则：
    - 连接池管理
    - 自动重连
    - 熔断保护
    """

    def __init__(self, prefetch_count: int = 5) -> None:
        """初始化消费者

        Args:
            prefetch_count: 预取消息数量，控制并发
        """
        settings = get_settings()
        self._host = settings.rabbitmq_host
        self._port = settings.rabbitmq_port
        self._user = settings.rabbitmq_user
        self._password = settings.rabbitmq_password
        self._queue = settings.rabbitmq_queue
        self._dlq = settings.rabbitmq_dlq

        self.prefetch_count = prefetch_count
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractRobustChannel] = None
        self._queue_obj = None
        self._exchange = None

        self.circuit_breaker = _message_breaker
        self._circuit_open_time: Optional[float] = None
        self._recovery_timeout = 30.0
        self._message_helper = get_mq_message_helper()

    async def connect(self) -> bool:
        """建立与 RabbitMQ 的强健连接"""
        try:
            self._connection = await aio_pika.connect_robust(
                host=self._host,
                port=self._port,
                login=self._user,
                password=self._password,
                heartbeat=300,
            )
            self._channel = await self._connection.channel()

            await self._channel.set_qos(prefetch_count=self.prefetch_count)

            self._queue_obj = await self._channel.declare_queue(self._queue, durable=True)
            await self._channel.declare_queue(self._dlq, durable=True)

            self._exchange = self._channel.default_exchange

            logger.info(
                f"RabbitMQConsumer connected: {self._host}:{self._port}, "
                f"prefetch={self.prefetch_count}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect RabbitMQ: {e}")
            raise

    async def _ensure_connected(self) -> None:
        """确保连接有效"""
        if self._connection is None or self._connection.is_closed:
            raise RuntimeError("Consumer not connected. Call await connect() first.")

    async def republish_to_back(
        self,
        original_msg: AbstractIncomingMessage,
        question_id: str,
        retry_count: int,
    ) -> bool:
        """降级：将失败的消息重新发布到队尾"""
        await self._ensure_connected()
        return await self._message_helper.republish_to_back(
            original_msg=original_msg,
            channel=self._channel,
            question_id=question_id,
            retry_count=retry_count,
        )

    async def _send_to_dlq(
        self,
        original_msg: AbstractIncomingMessage,
        question_id: str,
    ) -> bool:
        """死信处理"""
        await self._ensure_connected()
        return await self._message_helper._send_to_dlq(
            original_msg=original_msg,
            channel=self._channel,
            question_id=question_id,
        )

    async def _on_message(
        self,
        message: AbstractIncomingMessage,
        callback: Callable[[MQTaskMessage], Awaitable[bool]],
    ) -> None:
        """单条消息的并发协程处理逻辑"""

        # 熔断器拦截逻辑
        if isinstance(self.circuit_breaker.state, CircuitOpenState):
            if self._circuit_open_time and (
                time.time() - self._circuit_open_time >= self._recovery_timeout
            ):
                self.circuit_breaker.close()
                self._circuit_open_time = None
                logger.info("Circuit breaker recovered after timeout.")
            else:
                logger.warning("Circuit breaker is OPEN. Rejecting and requeueing...")
                await asyncio.sleep(2)
                await message.reject(requeue=True)
                return

        question_id = "unknown"
        retry_count = message.headers.get("x-retry-count", 0) if message.headers else 0

        try:
            task = MQTaskMessage.model_validate_json(message.body)
            question_id = task.question_id
            logger.info(f"Received task: q_id={question_id}, retry={retry_count}")

            success = await callback(task)

            if success:
                await message.ack()
                self.circuit_breaker.close()
            else:
                self.circuit_breaker.open()
                self._circuit_open_time = time.time()

                await message.ack()
                await self.republish_to_back(message, question_id, retry_count)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}. Message discarded.")
            await message.ack()

        except asyncio.CancelledError:
            logger.warning("Task cancelled, rejecting message to requeue...")
            await message.reject(requeue=True)
            raise

        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}")
            self.circuit_breaker.open()
            self._circuit_open_time = time.time()

            await message.reject(requeue=True)
            await self.republish_to_back(message, question_id, retry_count)

    async def consume(
        self,
        callback: Callable[[MQTaskMessage], Awaitable[bool]],
    ) -> None:
        """启动并发消费协程"""
        await self._ensure_connected()

        await self._queue_obj.consume(lambda msg: self._on_message(msg, callback))

        logger.info(f"Consumer is listening on '{self._queue}'...")

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("Consumer task was cancelled.")

    async def close(self) -> None:
        """优雅关闭连接"""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed gracefully.")


# 全局单例实例和锁
_consumer_instance: Optional[RabbitMQConsumer] = None
_consumer_lock = None


def _get_lock():
    """获取异步锁（延迟初始化）"""
    global _consumer_lock
    if _consumer_lock is None:
        _consumer_lock = asyncio.Lock()
    return _consumer_lock


async def get_consumer(prefetch_count: int = 5) -> RabbitMQConsumer:
    """获取异步消费者单例

    Args:
        prefetch_count: 预取消息数量，控制并发

    Returns:
        RabbitMQConsumer 实例
    """
    global _consumer_instance

    if _consumer_instance is not None:
        return _consumer_instance

    async with _get_lock():
        if _consumer_instance is not None:
            return _consumer_instance

        _consumer_instance = RabbitMQConsumer(prefetch_count=prefetch_count)
        await _consumer_instance.connect()
        return _consumer_instance


# 向后兼容的别名
AsyncRabbitMQConsumer = RabbitMQConsumer


__all__ = [
    "RabbitMQConsumer",
    "get_consumer",
    "AsyncRabbitMQConsumer",
]