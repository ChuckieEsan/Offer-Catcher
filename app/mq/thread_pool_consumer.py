"""线程池 RabbitMQ 消费者模块

使用 ThreadPoolExecutor 管理多个工作线程，每个线程创建独立的
aio-pika 连接和 channel 来消费消息队列中的数据。
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Optional, List

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger
from app.utils.circuit_breaker import create_circuit_breaker, CircuitOpenState


class ThreadPoolRabbitMQConsumer:
    """基于线程池的 RabbitMQ 消费者

    每个线程拥有独立的连接和 channel，实现真正的并发消费。
    适用于 CPU 密集型任务或需要隔离执行环境的场景。

    Features:
    - ThreadPoolExecutor 管理工作线程
    - 每个线程独立的 aio-pika 连接和 channel
    - 独立的事件循环
    - 熔断与降级机制
    """

    def __init__(self, num_threads: int = 4, prefetch_count: int = 1) -> None:
        """初始化线程池消费者

        Args:
            num_threads: 工作线程数量，默认 4
            prefetch_count: 每个线程的预取消息数量，默认 1
        """
        self.settings = get_settings()
        self.num_threads = num_threads
        self.prefetch_count = prefetch_count

        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: List[Future] = []
        self._running = True
        self._started = False

        # 为每个线程创建独立的熔断器
        self._circuit_breakers: dict[int, any] = {}

    def _create_circuit_breaker_for_thread(self, thread_id: int):
        """为每个线程创建独立的熔断器"""
        return create_circuit_breaker(
            fail_max=5,
            timeout_duration=30.0,
            name=f"rabbitmq_consumer_thread_{thread_id}",
        )

    def _consume_in_thread(self, thread_id: int, callback: Callable) -> None:
        """在线程中运行事件循环消费消息

        每个线程创建独立的连接、channel 和事件循环。

        Args:
            thread_id: 线程 ID
            callback: 消息处理回调函数
        """
        # 创建独立的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 为该线程创建独立的熔断器
        self._circuit_breakers[thread_id] = self._create_circuit_breaker_for_thread(thread_id)

        logger.info(f"Thread-{thread_id}: Starting consumer...")

        try:
            loop.run_until_complete(self._run_consumer_thread(thread_id, callback))
        except Exception as e:
            logger.error(f"Thread-{thread_id}: Consumer error: {e}")
        finally:
            loop.close()
            logger.info(f"Thread-{thread_id}: Consumer stopped")

    async def _run_consumer_thread(
        self, thread_id: int, callback: Callable[[MQTaskMessage], bool]
    ) -> None:
        """在线程中运行异步消费者

        Args:
            thread_id: 线程 ID
            callback: 消息处理回调函数
        """
        connection: Optional[AbstractRobustConnection] = None
        channel: Optional[AbstractRobustChannel] = None
        queue = None
        circuit_breaker = self._circuit_breakers[thread_id]
        circuit_open_time: Optional[float] = None
        recovery_timeout = 30.0

        try:
            # 建立独立连接
            connection = await aio_pika.connect_robust(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                login=self.settings.rabbitmq_user,
                password=self.settings.rabbitmq_password,
            )
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch_count)

            # 声明队列
            queue = await channel.declare_queue(
                self.settings.rabbitmq_queue, durable=True
            )

            logger.info(f"Thread-{thread_id}: Connected to queue: {self.settings.rabbitmq_queue}")

            # 消费循环
            while self._running:
                try:
                    # 获取消息（阻塞等待）
                    incoming_message = await queue.get()

                    # 熔断器逻辑
                    if isinstance(circuit_breaker.state, CircuitOpenState):
                        if circuit_open_time and (
                            time.time() - circuit_open_time >= recovery_timeout
                        ):
                            circuit_breaker.close()
                            circuit_open_time = None
                            logger.info(f"Thread-{thread_id}: Circuit breaker recovered")
                        else:
                            logger.warning(f"Thread-{thread_id}: Circuit breaker OPEN, requeue message")
                            await incoming_message.reject(requeue=True)
                            await asyncio.sleep(1)
                            continue

                    # 处理消息
                    success = await self._process_message(
                        incoming_message, callback, circuit_breaker, thread_id
                    )

                    if success:
                        await incoming_message.ack()
                        circuit_breaker.close()
                    else:
                        circuit_breaker.open()
                        circuit_open_time = time.time()
                        await incoming_message.ack()
                        # 重新入队
                        await self._republish_to_back(incoming_message, channel)

                except asyncio.CancelledError:
                    logger.info(f"Thread-{thread_id}: Task cancelled")
                    break
                except Exception as e:
                    logger.error(f"Thread-{thread_id}: Error in consume loop: {e}")
                    circuit_breaker.open()
                    circuit_open_time = time.time()
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Thread-{thread_id}: Connection error: {e}")
        finally:
            if channel and not channel.is_closed:
                await channel.close()
            if connection and not connection.is_closed:
                await connection.close()

    async def _process_message(
        self,
        message: AbstractIncomingMessage,
        callback: Callable[[MQTaskMessage], bool],
        circuit_breaker,
        thread_id: int,
    ) -> bool:
        """处理单条消息

        Args:
            message: 接收到的消息
            callback: 处理回调
            circuit_breaker: 熔断器
            thread_id: 线程 ID

        Returns:
            处理是否成功
        """
        question_id = "unknown"
        retry_count = message.headers.get("x-retry-count", 0) if message.headers else 0

        try:
            task = MQTaskMessage.model_validate_json(message.body)
            question_id = task.question_id
            logger.info(f"Thread-{thread_id}: Processing task {question_id}, retry={retry_count}")

            # 调用回调函数（同步版本，需要在线程池中执行）
            # 由于回调可能是同步的，我们直接调用
            success = callback(task)

            return success if success is not None else True

        except json.JSONDecodeError as e:
            logger.error(f"Thread-{thread_id}: Invalid JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Thread-{thread_id}: Error processing message: {e}")
            return False

    async def _republish_to_back(
        self, original_msg: AbstractIncomingMessage, channel: AbstractRobustChannel
    ) -> bool:
        """将失败消息重新发布到队尾

        Args:
            original_msg: 原始消息
            channel: channel 实例

        Returns:
            是否成功
        """
        retry_count = original_msg.headers.get("x-retry-count", 0) if original_msg.headers else 0
        new_retry_count = retry_count + 1

        if new_retry_count >= self.settings.rabbitmq_max_retries:
            # 转入死信队列
            return await self._send_to_dlq(original_msg, channel)

        try:
            msg = aio_pika.Message(
                body=original_msg.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-retry-count": new_retry_count},
            )
            await channel.default_exchange.publish(
                msg, routing_key=self.settings.rabbitmq_queue
            )
            return True
        except Exception as e:
            logger.error(f"Failed to republish message: {e}")
            return False

    async def _send_to_dlq(
        self, original_msg: AbstractIncomingMessage, channel: AbstractRobustChannel
    ) -> bool:
        """发送到死信队列

        Args:
            original_msg: 原始消息
            channel: channel 实例

        Returns:
            是否成功
        """
        try:
            msg = aio_pika.Message(
                body=original_msg.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-dead-letter": True},
            )
            await channel.default_exchange.publish(
                msg, routing_key=self.settings.rabbitmq_dlq
            )
            logger.warning("Message sent to DLQ (max retries exceeded)")
            return True
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
            return False

    async def start(self, callback: Callable[[MQTaskMessage], bool]) -> None:
        """启动线程池消费者

        Args:
            callback: 消息处理回调函数（同步函数）
        """
        if self._started:
            logger.warning("Consumer already started")
            return

        logger.info(f"Starting thread pool consumer with {self.num_threads} threads...")

        self._executor = ThreadPoolExecutor(max_workers=self.num_threads)
        self._running = True

        # 为每个线程提交消费任务
        for i in range(self.num_threads):
            future = self._executor.submit(self._consume_in_thread, i, callback)
            self._futures.append(future)

        self._started = True
        logger.info(f"Thread pool consumer started with {self.num_threads} threads")

    async def stop(self) -> None:
        """停止线程池消费者"""
        logger.info("Stopping thread pool consumer...")
        self._running = False

        # 等待所有线程完成
        for future in self._futures:
            try:
                future.result(timeout=5)
            except Exception as e:
                logger.warning(f"Error waiting for thread: {e}")

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        self._futures.clear()
        self._started = False
        logger.info("Thread pool consumer stopped")

    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._started and self._running


# 全局消费者实例
_thread_pool_consumer: Optional[ThreadPoolRabbitMQConsumer] = None


async def get_thread_pool_consumer(
    num_threads: int = 4, prefetch_count: int = 1
) -> ThreadPoolRabbitMQConsumer:
    """获取线程池消费者单例

    Args:
        num_threads: 工作线程数量
        prefetch_count: 每个线程的预取消息数量

    Returns:
        ThreadPoolRabbitMQConsumer 实例
    """
    global _thread_pool_consumer
    if _thread_pool_consumer is None:
        _thread_pool_consumer = ThreadPoolRabbitMQConsumer(
            num_threads=num_threads, prefetch_count=prefetch_count
        )
    return _thread_pool_consumer