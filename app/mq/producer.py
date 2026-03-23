"""RabbitMQ 消息生产者模块

提供消息发布功能，用于将需要异步生成答案的题目发送到队列。
"""

import json
from typing import Callable, Optional

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger


class RabbitMQProducer:
    """RabbitMQ 消息生产者

    提供以下核心功能：
    - 建立与 RabbitMQ 的连接
    - 发布单条或批量任务消息
    - 可靠的消息发布（带重试机制）
    - 连接管理
    """

    def __init__(self) -> None:
        """初始化生产者"""
        self.settings = get_settings()
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None

    def connect(self) -> bool:
        """建立与 RabbitMQ 的连接

        Returns:
            是否成功连接
        """
        try:
            # 构建连接参数
            parameters = pika.ConnectionParameters(
                host=self.settings.rabbitmq_host,
                port=self.settings.rabbitmq_port,
                credentials=pika.PlainCredentials(
                    self.settings.rabbitmq_user,
                    self.settings.rabbitmq_password,
                ),
                heartbeat=600,
                blocked_connection_timeout=300,
            )

            # 建立连接
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()

            # 声明队列（确保队列存在）
            self._channel.queue_declare(
                queue=self.settings.rabbitmq_queue,
                durable=True,  # 队列持久化
            )

            logger.info(
                f"RabbitMQ producer connected: {self.settings.rabbitmq_host}:"
                f"{self.settings.rabbitmq_port}"
            )
            return True

        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during connection: {e}")
            raise

    def _ensure_connected(self) -> None:
        """确保连接有效

        Raises:
            RuntimeError: 未连接或连接已关闭
        """
        if self._connection is None or self._connection.is_closed:
            raise RuntimeError("RabbitMQ producer is not connected. Call connect() first.")

    def publish_task(self, task: MQTaskMessage, retry: int = 3) -> bool:
        """发布单条任务消息

        Args:
            task: 任务消息
            retry: 发布失败时的重试次数

        Returns:
            是否发布成功
        """
        self._ensure_connected()

        for attempt in range(retry):
            try:
                # 序列化消息
                body = task.model_dump_json()

                # 发布消息
                self._channel.basic_publish(
                    exchange="",
                    routing_key=self.settings.rabbitmq_queue,
                    body=body.encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # 消息持久化
                        content_type="application/json",
                    ),
                )

                logger.info(
                    f"Published task: question_id={task.question_id}, "
                    f"company={task.company}"
                )
                return True

            except (AMQPConnectionError, AMQPChannelError) as e:
                logger.warning(
                    f"Publish attempt {attempt + 1}/{retry} failed: {e}. "
                    "Reconnecting..."
                )
                self.connect()  # 重新连接

            except Exception as e:
                logger.error(f"Failed to publish task: {e}")
                raise

        logger.error(f"Failed to publish task after {retry} attempts")
        return False

    def publish_tasks(self, tasks: list[MQTaskMessage]) -> int:
        """批量发布任务消息

        Args:
            tasks: 任务消息列表

        Returns:
            成功发布的数量
        """
        success_count = 0

        for task in tasks:
            if self.publish_task(task):
                success_count += 1

        logger.info(f"Published {success_count}/{len(tasks)} tasks")
        return success_count

    def close(self) -> None:
        """关闭连接"""
        if self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
                logger.info("RabbitMQ producer connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None
                self._channel = None

    def __enter__(self) -> "RabbitMQProducer":
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """上下文管理器退出"""
        self.close()


# 全局单例
_producer: Optional[RabbitMQProducer] = None


def get_producer() -> RabbitMQProducer:
    """获取生产者单例

    Returns:
        RabbitMQProducer 实例
    """
    global _producer
    if _producer is None:
        _producer = RabbitMQProducer()
    return _producer