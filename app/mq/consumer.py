"""RabbitMQ 消息消费者模块

提供消息消费功能，用于后台 Worker 消费队列中的任务并生成答案。
"""

import json
from typing import Callable, Optional

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from app.config.settings import get_settings
from app.models.schemas import MQTaskMessage
from app.utils.logger import logger


class RabbitMQConsumer:
    """RabbitMQ 消息消费者

    提供以下核心功能：
    - 建立与 RabbitMQ 的连接
    - 启动消费循环
    - 支持手动 ACK/Nack
    - 可设置 prefetch_count 控制并发
    - 连接管理
    """

    def __init__(self, prefetch_count: int = 1) -> None:
        """初始化消费者

        Args:
            prefetch_count: 预取消息数量，控制并发
        """
        self.settings = get_settings()
        self.prefetch_count = prefetch_count
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._consuming = False

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

            # 设置 QoS（预取数量）
            self._channel.basic_qos(prefetch_count=self.prefetch_count)

            logger.info(
                f"RabbitMQ consumer connected: {self.settings.rabbitmq_host}:"
                f"{self.settings.rabbitmq_port}, prefetch={self.prefetch_count}"
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
            raise RuntimeError("RabbitMQ consumer is not connected. Call connect() first.")

    def acknowledge(self, delivery_tag: int) -> None:
        """确认消息已被处理

        Args:
            delivery_tag: 消息传递标签
        """
        self._ensure_connected()
        try:
            self._channel.basic_ack(delivery_tag=delivery_tag)
            logger.debug(f"Acknowledged message: {delivery_tag}")
        except Exception as e:
            logger.error(f"Failed to acknowledge message: {e}")

    def reject(self, delivery_tag: int, requeue: bool = False) -> None:
        """拒绝消息

        Args:
            delivery_tag: 消息传递标签
            requeue: 是否重新入队
        """
        self._ensure_connected()
        try:
            self._channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
            logger.debug(f"Rejected message: {delivery_tag}, requeue={requeue}")
        except Exception as e:
            logger.error(f"Failed to reject message: {e}")

    def _on_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
        callback: Callable[[MQTaskMessage], bool],
    ) -> None:
        """消息回调处理

        Args:
            channel: 通道
            method: 传递方法
            properties: 消息属性
            body: 消息体
            callback: 业务处理回调函数
        """
        try:
            # 解析消息
            task = MQTaskMessage.model_validate_json(body)
            logger.info(
                f"Received task: question_id={task.question_id}, "
                f"company={task.company}, position={task.position}"
            )

            # 调用业务处理函数
            success = callback(task)

            # 根据处理结果进行 ACK 或 Nack
            if success:
                self.acknowledge(method.delivery_tag)
            else:
                # 处理失败，重新入队
                self.reject(method.delivery_tag, requeue=True)
                logger.warning(
                    f"Task processing failed, requeued: question_id={task.question_id}"
                )

        except json.JSONDecodeError as e:
            # 消息格式错误，不再重新入队
            logger.error(f"Invalid message format: {e}")
            self.reject(method.delivery_tag, requeue=False)

        except Exception as e:
            # 其他异常，重新入队
            logger.error(f"Error processing message: {e}")
            self.reject(method.delivery_tag, requeue=True)

    def consume(
        self,
        callback: Callable[[MQTaskMessage], bool],
        auto_reconnect: bool = True,
    ) -> None:
        """启动消费循环

        Args:
            callback: 业务处理回调函数，接收 MQTaskMessage，返回是否处理成功
            auto_reconnect: 连接断开时是否自动重连
        """
        self._ensure_connected()
        self._consuming = True

        # 设置消息回调
        self._channel.basic_consume(
            queue=self.settings.rabbitmq_queue,
            on_message_callback=lambda ch, method, props, body: self._on_message(
                ch, method, props, body, callback
            ),
            auto_ack=False,  # 手动 ACK
        )

        logger.info(f"Starting to consume from queue: {self.settings.rabbitmq_queue}")

        try:
            # 开始消费
            while self._consuming:
                self._connection.process_data_events(time_limit=1)
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
            self.stop_consuming()
        except (AMQPConnectionError, AMQPChannelError) as e:
            logger.error(f"Consumer connection error: {e}")
            if auto_reconnect:
                self._reconnect_and_consume(callback)
            else:
                raise
        except Exception as e:
            logger.error(f"Unexpected error in consumer: {e}")
            raise

    def _reconnect_and_consume(
        self, callback: Callable[[MQTaskMessage], bool]
    ) -> None:
        """重连并继续消费

        Args:
            callback: 业务处理回调函数
        """
        max_retries = 5
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                logger.info(f"Reconnecting... (attempt {attempt + 1}/{max_retries})")
                self.connect()
                self.consume(callback, auto_reconnect=True)
                return
            except Exception as e:
                logger.warning(f"Reconnect failed: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)

        logger.error("Failed to reconnect after max retries")

    def stop_consuming(self) -> None:
        """停止消费"""
        self._consuming = False
        if self._channel:
            try:
                self._channel.stop_consuming()
            except Exception as e:
                logger.warning(f"Error stopping consume: {e}")
        logger.info("Consumer stopped consuming")

    def close(self) -> None:
        """关闭连接"""
        self.stop_consuming()
        if self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
                logger.info("RabbitMQ consumer connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None
                self._channel = None

    def __enter__(self) -> "RabbitMQConsumer":
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
_consumer: Optional[RabbitMQConsumer] = None


def get_consumer(prefetch_count: int = 1) -> RabbitMQConsumer:
    """获取消费者单例

    Args:
        prefetch_count: 预取消息数量

    Returns:
        RabbitMQConsumer 实例
    """
    global _consumer
    if _consumer is None:
        _consumer = RabbitMQConsumer(prefetch_count=prefetch_count)
    return _consumer