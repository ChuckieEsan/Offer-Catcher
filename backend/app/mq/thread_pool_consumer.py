"""线程池 RabbitMQ 消费者模块

使用 ThreadPoolExecutor 管理多个工作线程，每个线程创建独立的
aio-pika 连接和 channel 来消费消息队列中的数据。
"""

import asyncio
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, List, Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage
from aiobreaker import CircuitBreaker

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.mq.message_helper import get_mq_message_helper
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
        self._message_helper = get_mq_message_helper()

        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: List[Future] = []
        self._running = True
        self._started = False

        # 每个线程的熔断器打开时间（类级别存储）
        self._circuit_open_times: dict[int, Optional[float]] = {}

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

        # 为每个线程创建独立的熔断器
        circuit_breakers = {
            i: create_circuit_breaker(
                fail_max=5,
                timeout_duration=30.0,
                name=f"rabbitmq_consumer_thread_{i}",
            )
            for i in range(self.num_threads)
        }

        # 为每个线程提交消费任务
        for i in range(self.num_threads):
            future = self._executor.submit(
                self._consume_in_thread, i, callback, circuit_breakers[i]
            )
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

    def _consume_in_thread(
        self,
        thread_id: int,
        callback: Callable,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """在线程中运行事件循环消费消息

        每个线程创建独立的连接、channel 和事件循环。

        Args:
            thread_id: 线程 ID
            callback: 消息处理回调函数
            circuit_breaker: 该线程的熔断器
        """
        # 创建独立的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        logger.info(f"Thread-{thread_id}: Starting consumer...")

        try:
            loop.run_until_complete(
                self._run_consumer_thread(thread_id, callback, circuit_breaker)
            )
        except Exception as e:
            logger.error(f"Thread-{thread_id}: Consumer error: {e}")
        finally:
            loop.close()
            logger.info(f"Thread-{thread_id}: Consumer stopped")

    async def _run_consumer_thread(
        self,
        thread_id: int,
        callback: Callable[[MQTaskMessage], bool],
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """在线程中运行异步消费者

        Args:
            thread_id: 线程 ID
            callback: 消息处理回调函数
            circuit_breaker: 熔断器实例
        """
        connection: Optional[AbstractRobustConnection] = None
        channel: Optional[AbstractRobustChannel] = None

        try:
            # 建立独立连接，heartbeat=300 避免长任务导致连接断开
            connection = await aio_pika.connect_robust(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                login=self.settings.rabbitmq_user,
                password=self.settings.rabbitmq_password,
                heartbeat=300,
            )
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch_count)

            # 声明队列
            queue = await channel.declare_queue(
                self.settings.rabbitmq_queue, durable=True
            )

            logger.info(f"Thread-{thread_id}: Connected to queue: {self.settings.rabbitmq_queue}")

            # 使用 consume 回调模式 - 有新消息时自动调用，不会空转
            await queue.consume(
                lambda msg: self._on_message_callback(
                    msg, thread_id, callback, circuit_breaker, channel
                )
            )

            # 挂起保持消费
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"Thread-{thread_id}: Task cancelled")
        except Exception as e:
            logger.error(f"Thread-{thread_id}: Connection error: {e}")
        finally:
            if channel and not channel.is_closed:
                await channel.close()
            if connection and not connection.is_closed:
                await connection.close()

    async def _on_message_callback(
        self,
        message: AbstractIncomingMessage,
        thread_id: int,
        callback: Callable[[MQTaskMessage], bool],
        circuit_breaker: CircuitBreaker,
        channel: AbstractRobustChannel,
    ) -> None:
        """消息回调处理

        处理接收到的 RabbitMQ 消息，包括熔断器检查、消息处理和结果确认。

        Args:
            message: 接收到的消息
            thread_id: 线程 ID
            callback: 业务回调函数
            circuit_breaker: 熔断器
            channel: channel 实例
        """
        recovery_timeout = 30.0

        # 熔断器拦截逻辑
        if isinstance(circuit_breaker.state, CircuitOpenState):
            circuit_open_time = self._circuit_open_times.get(thread_id)
            if circuit_open_time and (
                time.time() - circuit_open_time >= recovery_timeout
            ):
                circuit_breaker.close()
                self._circuit_open_times[thread_id] = None
                logger.info(f"Thread-{thread_id}: Circuit breaker recovered")
            else:
                logger.warning(f"Thread-{thread_id}: Circuit breaker OPEN, requeue message")
                await message.reject(requeue=True)
                return

        # 处理消息
        success = await self._process_message(
            message, callback, thread_id
        )

        if success:
            await message.ack()
            circuit_breaker.close()
            self._circuit_open_times[thread_id] = None
        else:
            circuit_breaker.open()
            self._circuit_open_times[thread_id] = time.time()
            await message.ack()
            await self._republish_to_back(message, channel)

    async def _process_message(
        self,
        message: AbstractIncomingMessage,
        callback: Callable[[MQTaskMessage], bool],
        thread_id: int,
    ) -> bool:
        """处理单条消息

        Args:
            message: 接收到的消息
            callback: 处理回调（可以是同步或异步函数）
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

            # 调用回调函数 - 支持同步和异步回调
            result = callback(task)

            # 如果返回的是协程，需要 await
            if inspect.iscoroutine(result):
                success = await result
            else:
                success = result

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
        """将失败消息重新发布到队尾"""
        retry_count = original_msg.headers.get("x-retry-count", 0) if original_msg.headers else 0
        question_id = "unknown"
        try:
            task = MQTaskMessage.model_validate_json(original_msg.body)
            question_id = task.question_id
        except Exception:
            pass

        return await self._message_helper.republish_to_back(
            original_msg=original_msg,
            channel=channel,
            question_id=question_id,
            retry_count=retry_count,
        )

    async def _send_to_dlq(
        self, original_msg: AbstractIncomingMessage, channel: AbstractRobustChannel
    ) -> bool:
        """发送到死信队列"""
        question_id = "unknown"
        try:
            task = MQTaskMessage.model_validate_json(original_msg.body)
            question_id = task.question_id
        except Exception:
            pass

        return await self._message_helper._send_to_dlq(
            original_msg=original_msg,
            channel=channel,
            question_id=question_id,
        )


# 全局单例实例和锁
_consumer_instance: Optional[ThreadPoolRabbitMQConsumer] = None
_consumer_lock = None


def _get_lock():
    """获取异步锁（延迟初始化）"""
    global _consumer_lock
    if _consumer_lock is None:
        _consumer_lock = asyncio.Lock()
    return _consumer_lock


async def get_thread_pool_consumer(
    num_threads: int = 4, prefetch_count: int = 1
) -> ThreadPoolRabbitMQConsumer:
    """获取线程池消费者单例

    手动实现异步单例模式。

    Note: 参数在首次调用后会被忽略。
    """
    global _consumer_instance

    if _consumer_instance is not None:
        return _consumer_instance

    async with _get_lock():
        if _consumer_instance is not None:
            return _consumer_instance

        _consumer_instance = ThreadPoolRabbitMQConsumer(
            num_threads=num_threads, prefetch_count=prefetch_count
        )
        return _consumer_instance