"""异步 RabbitMQ 消息生产者模块 (基于 aio-pika)

提供消息发布功能，用于将需要异步生成答案的题目发送到队列。
"""

from typing import Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel
from aio_pika import Message, DeliveryMode

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.utils.cache import singleton
from app.utils.logger import logger


class AsyncRabbitMQProducer:
    """基于 aio-pika 的异步消息生产者

    提供以下核心功能：
    - 建立与 RabbitMQ 的强健连接（自动处理断线重连）
    - 发布单条或批量任务消息
    - 可靠的消息发布（带重试机制）
    - 连接管理
    """

    def __init__(self) -> None:
        """初始化生产者"""
        self.settings = get_settings()
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractRobustChannel] = None
        self._exchange = None

    async def connect(self) -> bool:
        """建立与 RabbitMQ 的强健连接"""
        try:
            # connect_robust 会在网络抖动时自动重连
            self._connection = await aio_pika.connect_robust(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                login=self.settings.rabbitmq_user,
                password=self.settings.rabbitmq_password,
            )
            self._channel = await self._connection.channel()

            # 声明队列（确保队列存在）
            await self._channel.declare_queue(
                self.settings.rabbitmq_queue,
                durable=True,
            )

            # 获取默认 Exchange
            self._exchange = self._channel.default_exchange

            logger.info(
                f"Async RabbitMQ producer connected: {self.settings.rabbitmq_host}:"
                f"{self.settings.rabbitmq_port}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect Async RabbitMQ: {e}")
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
            # 处理 "no running event loop" 错误，重新创建连接
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
                # 序列化消息
                body = task.model_dump_json()

                # 发布消息
                msg = Message(
                    body=body.encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    message_id=task.question_id,
                )

                await self._exchange.publish(
                    msg,
                    routing_key=self.settings.rabbitmq_queue,
                )

                logger.info(
                    f"Published task: question_id={task.question_id}, "
                    f"company={task.company}"
                )
                return True

            except Exception as e:
                logger.warning(
                    f"Publish attempt {attempt + 1}/{retry} failed: {e}. "
                    "Reconnecting..."
                )
                await self.connect()  # 重新连接

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
            cleanup: 如果为 True，则关闭连接并重置单例（仅在程序退出时使用）
        """
        try:
            if self._connection is None:
                return

            if not self._connection.is_closed:
                await self._connection.close()
                logger.info("RabbitMQ producer connection closed")
        except RuntimeError as e:
            # 处理 "no running event loop" 错误
            if "event loop" in str(e).lower():
                logger.warning(f"Cannot close connection: {e}")
            else:
                logger.warning(f"Error closing connection: {e}")
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
        finally:
            self._connection = None
            self._channel = None
            # 仅在明确需要清理时重置单例
            if cleanup:
                get_producer.clear_cache()


@singleton
async def get_producer() -> AsyncRabbitMQProducer:
    """获取异步生产者单例

    Returns:
        AsyncRabbitMQProducer 实例
    """
    producer = AsyncRabbitMQProducer()
    await producer.connect()
    return producer
