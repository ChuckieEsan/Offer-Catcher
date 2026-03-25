"""异步 RabbitMQ 消息消费者模块 (基于 aio-pika)

提供高并发的协程消息消费功能。
支持断路器与降级机制（重新入队与死信队列 DLQ）。
"""

import asyncio
import json
import time
from typing import Callable, Optional, Awaitable

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger
from app.utils.circuit_breaker import create_circuit_breaker, CircuitOpenState

# 创建消费者专用的断路器
_message_breaker = create_circuit_breaker(
    fail_max=5,
    timeout_duration=30.0,
    name="rabbitmq_consumer",
)


class AsyncRabbitMQConsumer:
    """基于 aio-pika 的异步消息消费者

    提供以下核心功能：
    - 建立与 RabbitMQ 的强健连接（自动处理断线重连）
    - 启动并发消费协程
    - 支持手动 ACK/Nack
    - 可设置 prefetch_count 控制并发
    - 连接管理
    - 熔断与降级机制（基于 aiobreaker）
    """

    def __init__(self, prefetch_count: int = 5) -> None:
        """初始化消费者

        Args:
            prefetch_count: 预取消息数量，控制并发
        """
        self.settings = get_settings()
        self.prefetch_count = prefetch_count
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractRobustChannel] = None
        self._queue = None
        self._exchange = None

        self.circuit_breaker = _message_breaker
        self._circuit_open_time: Optional[float] = None
        self._recovery_timeout = 30.0

    async def connect(self) -> bool:
        """建立与 RabbitMQ 的强健连接（自动处理断线重连）"""
        try:
            # connect_robust 会在网络抖动时自动在底层重连并恢复队列
            self._connection = await aio_pika.connect_robust(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                login=self.settings.rabbitmq_user,
                password=self.settings.rabbitmq_password,
            )
            self._channel = await self._connection.channel()

            # 设置 QoS 控制最大并发协程数
            await self._channel.set_qos(prefetch_count=self.prefetch_count)

            # 声明队列 (保证幂等性)
            self._queue = await self._channel.declare_queue(
                self.settings.rabbitmq_queue, durable=True
            )
            # 声明死信队列 DLQ
            await self._channel.declare_queue(
                self.settings.rabbitmq_dlq, durable=True
            )

            # 获取默认 Exchange 用于重新发布消息
            self._exchange = self._channel.default_exchange

            logger.info(
                f"Async RabbitMQ connected: {self.settings.rabbitmq_host}:"
                f"{self.settings.rabbitmq_port}, prefetch={self.prefetch_count}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect Async RabbitMQ: {e}")
            raise

    async def _ensure_connected(self) -> None:
        if self._connection is None or self._connection.is_closed:
            raise RuntimeError("Consumer not connected. Call await connect() first.")

    async def republish_to_back(
        self, original_msg: AbstractIncomingMessage, question_id: str, retry_count: int
    ) -> bool:
        """降级：将失败的消息重新发布到队尾"""
        await self._ensure_connected()
        new_retry_count = retry_count + 1

        # 若超过最大重试次数，转入死信队列
        if new_retry_count >= self.settings.rabbitmq_max_retries:
            return await self._send_to_dlq(original_msg, question_id)

        try:
            # 构造新的 Message，附带递增的 retry-count
            msg = aio_pika.Message(
                body=original_msg.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-retry-count": new_retry_count},
            )
            await self._exchange.publish(
                msg, routing_key=self.settings.rabbitmq_queue
            )
            logger.info(
                f"Message republished to back: q_id={question_id}, retry={new_retry_count}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to republish message: {e}")
            return False

    async def _send_to_dlq(
        self, original_msg: AbstractIncomingMessage, question_id: str
    ) -> bool:
        """死信处理"""
        try:
            msg = aio_pika.Message(
                body=original_msg.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-dead-letter": True},
            )
            await self._exchange.publish(
                msg, routing_key=self.settings.rabbitmq_dlq
            )
            logger.warning(
                f"Message sent to DLQ (max retries exceeded): q_id={question_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
            return False

    async def _on_message(
        self,
        message: AbstractIncomingMessage,
        callback: Callable[[MQTaskMessage], Awaitable[bool]],
    ) -> None:
        """单条消息的并发协程处理逻辑"""

        # 使用 process() 上下文，ignore_processed=True 允许我们手动控制 ack/reject
        async with message.process(ignore_processed=True):

            # --- 1. 熔断器拦截逻辑 ---
            if isinstance(self.circuit_breaker.state, CircuitOpenState):
                if self._circuit_open_time and (
                    time.time() - self._circuit_open_time >= self._recovery_timeout
                ):
                    self.circuit_breaker.close()
                    self._circuit_open_time = None
                    logger.info("Circuit breaker recovered after timeout.")
                else:
                    # 正在熔断中：拒绝该消息使其重新排队，并短暂休眠防止 CPU 狂转
                    logger.warning("Circuit breaker is OPEN. Rejecting and requeueing...")
                    await asyncio.sleep(2)
                    await message.reject(requeue=True)
                    return

            # --- 2. 正常业务逻辑 ---
            question_id = "unknown"
            retry_count = (
                message.headers.get("x-retry-count", 0) if message.headers else 0
            )

            try:
                task = MQTaskMessage.model_validate_json(message.body)
                question_id = task.question_id
                logger.info(
                    f"Received task: q_id={question_id}, retry={retry_count}"
                )

                # 执行异步的大模型调用回调
                success = await callback(task)

                if success:
                    await message.ack()
                    self.circuit_breaker.close()
                else:
                    # 业务明确返回失败：打开熔断器，原消息ACK，重新投递到队尾
                    self.circuit_breaker.open()
                    self._circuit_open_time = time.time()

                    await message.ack()
                    await self.republish_to_back(message, question_id, retry_count)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON format: {e}. Message discarded.")
                await message.ack()  # 脏数据直接丢弃，不重试

            except Exception as e:
                logger.error(f"Unexpected error processing message: {e}")
                self.circuit_breaker.open()
                self._circuit_open_time = time.time()

                await message.ack()
                await self.republish_to_back(message, question_id, retry_count)

    async def consume(
        self, callback: Callable[[MQTaskMessage], Awaitable[bool]]
    ) -> None:
        """启动并发消费协程"""
        await self._ensure_connected()

        # aio-pika 会自动根据 prefetch_count 并发拉起 _on_message 协程
        await self._queue.consume(lambda msg: self._on_message(msg, callback))

        logger.info(f"Async Consumer is listening on '{self.settings.rabbitmq_queue}'...")

        # 挂起当前协程，维持消费循环
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("Consumer task was cancelled.")

    async def close(self) -> None:
        """优雅关闭连接"""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed gracefully.")


# 全局单例
_consumer: Optional[AsyncRabbitMQConsumer] = None


async def get_consumer(prefetch_count: int = 5) -> AsyncRabbitMQConsumer:
    """获取异步消费者单例

    Args:
        prefetch_count: 预取消息数量，控制并发

    Returns:
        AsyncRabbitMQConsumer 实例
    """
    global _consumer
    if _consumer is None:
        _consumer = AsyncRabbitMQConsumer(prefetch_count=prefetch_count)
        await _consumer.connect()
    return _consumer