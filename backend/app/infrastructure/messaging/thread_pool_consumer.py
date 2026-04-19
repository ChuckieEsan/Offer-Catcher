"""RabbitMQ 线程池消费者模块

使用 ThreadPoolExecutor 管理多个工作线程，每个线程创建独立的
aio-pika 连接和 channel 来消费消息队列中的数据。
作为基础设施层消息组件，为应用层提供消息消费服务。
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

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger
from app.infrastructure.messaging.message_helper import get_mq_message_helper
from app.infrastructure.messaging.messages import MQTaskMessage
from app.infrastructure.common.circuit_breaker import create_circuit_breaker, CircuitOpenState


class ThreadPoolRabbitMQConsumer:
    """基于线程池的 RabbitMQ 消费者

    每个线程拥有独立的连接和 channel，实现真正的并发消费。
    适用于 CPU 密集型任务或需要隔离执行环境的场景。

    设计原则：
    - 线程池管理
    - 独立连接和事件循环
    - 熔断保护
    """

    def __init__(self, num_threads: int = 4, prefetch_count: int = 1) -> None:
        """初始化线程池消费者

        Args:
            num_threads: 工作线程数量，默认 4
            prefetch_count: 每个线程的预取消息数量，默认 1
        """
        settings = get_settings()
        self._host = settings.rabbitmq_host
        self._port = settings.rabbitmq_port
        self._user = settings.rabbitmq_user
        self._password = settings.rabbitmq_password
        self._queue = settings.rabbitmq_queue

        self.num_threads = num_threads
        self.prefetch_count = prefetch_count
        self._message_helper = get_mq_message_helper()

        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: List[Future] = []
        self._running = True
        self._started = False

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

        circuit_breakers = {
            i: create_circuit_breaker(
                fail_max=5,
                timeout_duration=30.0,
                name=f"rabbitmq_consumer_thread_{i}",
            )
            for i in range(self.num_threads)
        }

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
        """在线程中运行事件循环消费消息"""
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
        """在线程中运行异步消费者"""
        connection: Optional[AbstractRobustConnection] = None
        channel: Optional[AbstractRobustChannel] = None

        try:
            connection = await aio_pika.connect_robust(
                host=self._host,
                port=self._port,
                login=self._user,
                password=self._password,
                heartbeat=300,
            )
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch_count)

            queue = await channel.declare_queue(self._queue, durable=True)

            logger.info(f"Thread-{thread_id}: Connected to queue: {self._queue}")

            await queue.consume(
                lambda msg: self._on_message_callback(
                    msg, thread_id, callback, circuit_breaker, channel
                )
            )

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
        """消息回调处理"""
        recovery_timeout = 30.0

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

        success = await self._process_message(message, callback, thread_id)

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
        """处理单条消息"""
        question_id = "unknown"
        retry_count = message.headers.get("x-retry-count", 0) if message.headers else 0

        try:
            task = MQTaskMessage.model_validate_json(message.body)
            question_id = task.question_id
            logger.info(f"Thread-{thread_id}: Processing task {question_id}, retry={retry_count}")

            result = callback(task)

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
        self,
        original_msg: AbstractIncomingMessage,
        channel: AbstractRobustChannel,
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

    Args:
        num_threads: 工作线程数量
        prefetch_count: 每个线程的预取消息数量

    Returns:
        ThreadPoolRabbitMQConsumer 实例
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


__all__ = [
    "ThreadPoolRabbitMQConsumer",
    "get_thread_pool_consumer",
]