"""异步 RabbitMQ 消息消费者模块 (基于 aio-pika)

提供高并发的协程消息消费功能。
支持断路器与降级机制（重新入队与死信队列 DLQ）。
"""

import asyncio
import json
import time
from typing import Callable, Awaitable

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.mq.message_helper import get_mq_message_helper
from app.utils.cache import singleton
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
        self._message_helper = get_mq_message_helper()

    async def connect(self) -> bool:
        """建立与 RabbitMQ 的强健连接（自动处理断线重连）"""
        try:
            # connect_robust 会在网络抖动时自动在底层重连并恢复队列
            # heartbeat=300 避免长任务导致连接断开
            self._connection = await aio_pika.connect_robust(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                login=self.settings.rabbitmq_user,
                password=self.settings.rabbitmq_password,
                heartbeat=300,
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
        """确保连接有效

        Raises:
            RuntimeError: 如果未连接
        """
        if self._connection is None or self._connection.is_closed:
            raise RuntimeError("Consumer not connected. Call await connect() first.")

    async def republish_to_back(
        self, original_msg: AbstractIncomingMessage, question_id: str, retry_count: int
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
        self, original_msg: AbstractIncomingMessage, question_id: str
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

        # 不使用 process() 上下文，手动控制 ACK/Reject
        # 避免程序中断时消息被意外 ACK

        # --- 1. 熔断器拦截逻辑 ---
        if isinstance(self.circuit_breaker.state, CircuitOpenState):
            if self._circuit_open_time and (
                time.time() - self._circuit_open_time >= self._recovery_timeout
            ):
                self.circuit_breaker.close()
                self._circuit_open_time = None
                logger.info("Circuit breaker recovered after timeout.")
            else:
                # 正在熔断中：拒绝该消息使其重新排队
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

        except asyncio.CancelledError:
            # 处理程序被中断的情况：不 ACK，消息会重新入队
            logger.warning("Task cancelled, rejecting message to requeue...")
            await message.reject(requeue=True)
            raise  # 重新抛出 CancelledError

        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}")
            self.circuit_breaker.open()
            self._circuit_open_time = time.time()

            # 异常情况下拒绝消息，让其重新入队
            await message.reject(requeue=True)
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


@singleton
async def get_consumer(prefetch_count: int = 5) -> AsyncRabbitMQConsumer:
    """获取异步消费者单例

    Note: 参数在首次调用后会被忽略。

    Args:
        prefetch_count: 预取消息数量，控制并发

    Returns:
        AsyncRabbitMQConsumer 实例
    """
    consumer = AsyncRabbitMQConsumer(prefetch_count=prefetch_count)
    await consumer.connect()
    return consumer