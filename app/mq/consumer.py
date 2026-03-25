"""RabbitMQ 消息消费者模块

提供消息消费功能，用于后台 Worker 消费队列中的任务并生成答案。
支持断路器与降级机制（基于 app/utils/circuit_breaker）：
- 断路器：连续失败达到阈值后暂停消费
- 降级：失败消息重新入队到队尾
"""

from typing import Callable, Optional
import json
import time

import pika
from pika import BlockingConnection
from pika.channel import Channel
from pika.exceptions import AMQPConnectionError, AMQPChannelError

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


class RabbitMQConsumer:
    """RabbitMQ 消息消费者

    提供以下核心功能：
    - 建立与 RabbitMQ 的连接
    - 启动消费循环
    - 支持手动 ACK/Nack
    - 可设置 prefetch_count 控制并发
    - 连接管理
    - 熔断与降级机制（基于 aiobreaker）
    """

    def __init__(
        self,
        prefetch_count: int = 1,
    ) -> None:
        """初始化消费者

        Args:
            prefetch_count: 预取消息数量，控制并发
        """
        self.settings = get_settings()
        self.prefetch_count = prefetch_count
        self._connection: Optional[BlockingConnection] = None
        self._channel: Optional[Channel] = None
        self._consuming = False
        # 引用断路器
        self.circuit_breaker = _message_breaker
        # 记录熔断打开的时间（用于恢复检查）
        self._circuit_open_time: Optional[float] = None
        # 恢复超时时间（秒）
        self._recovery_timeout = 30

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

            # 声明死信队列
            self._channel.queue_declare(
                queue=self.settings.rabbitmq_dlq,
                durable=True,
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

    def republish_to_back(self, body: bytes, question_id: str, retry_count: int = 0) -> bool:
        """降级处理：将消息重新发布到队尾，或发送到死信队列

        Args:
            body: 消息体
            question_id: 题目ID，用于日志
            retry_count: 当前重试次数

        Returns:
            是否发布成功
        """
        self._ensure_connected()

        # 检查是否超过最大重试次数
        if retry_count >= self.settings.rabbitmq_max_retries:
            # 发送到死信队列
            return self._send_to_dlq(body, question_id)

        # 发送到队尾
        new_retry_count = retry_count + 1
        try:
            self._channel.basic_publish(
                exchange="",
                routing_key=self.settings.rabbitmq_queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 消息持久化
                    content_type="application/json",
                    headers={"x-retry-count": new_retry_count},
                ),
            )
            logger.info(
                f"Message republished to back of queue: question_id={question_id}, "
                f"retry={new_retry_count}/{self.settings.rabbitmq_max_retries}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to republish message: {e}")
            return False

    def _send_to_dlq(self, body: bytes, question_id: str) -> bool:
        """发送到死信队列

        Args:
            body: 消息体
            question_id: 题目ID，用于日志

        Returns:
            是否发送成功
        """
        self._ensure_connected()
        try:
            self._channel.basic_publish(
                exchange="",
                routing_key=self.settings.rabbitmq_dlq,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 消息持久化
                    content_type="application/json",
                    headers={"x-dead-letter": True},
                ),
            )
            logger.warning(
                f"Message sent to DLQ (max retries exceeded): question_id={question_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
            return False

    def _on_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
        callback: Callable[[MQTaskMessage], bool],
    ) -> None:
        """消息回调处理

        集成熔断与降级机制：
        - 成功处理后重置熔断计数器
        - 失败处理后记录失败次数
        - 消息格式错误直接丢弃
        - 业务异常使用降级处理（重新发布到队尾）

        Args:
            channel: 通道
            method: 传递方法
            properties: 消息属性
            body: 消息体
            callback: 业务处理回调函数
        """
        question_id = "unknown"
        # 从消息头获取重试次数
        retry_count = 0
        if properties.headers and "x-retry-count" in properties.headers:
            retry_count = properties.headers["x-retry-count"]

        try:
            # 解析消息
            task = MQTaskMessage.model_validate_json(body)
            question_id = task.question_id
            logger.info(
                f"Received task: question_id={task.question_id}, "
                f"company={task.company}, position={task.position}, retry={retry_count}"
            )

            # 调用业务处理函数
            success = callback(task)

            # 根据处理结果进行 ACK 或降级处理
            if success:
                self.acknowledge(method.delivery_tag)
                self.circuit_breaker.close()  # 成功则关闭熔断器
                logger.debug(f"Task processed successfully: question_id={question_id}")
            else:
                # 业务返回失败，记录失败次数并降级处理
                self.circuit_breaker.open()  # 打开熔断器
                self._circuit_open_time = time.time()  # 记录打开时间
                # 先确认原消息
                self.acknowledge(method.delivery_tag)
                # 降级：重新发布到队尾（带重试次数）
                self.republish_to_back(body, question_id, retry_count)
                logger.warning(
                    f"Task processing failed, degraded: question_id={question_id}"
                )

        except json.JSONDecodeError as e:
            # 消息格式错误，不再重新入队，直接丢弃
            logger.error(f"Invalid message format: {e}, message discarded")
            self.acknowledge(method.delivery_tag)

        except Exception as e:
            # 其他异常，记录失败并降级处理
            self.circuit_breaker.open()  # 打开熔断器
            logger.error(f"Error processing message: {e}")
            # 先确认原消息
            self.acknowledge(method.delivery_tag)
            # 降级：重新发布到队尾（带重试次数）
            self.republish_to_back(body, question_id, retry_count)
            logger.warning(
                f"Message error, degraded: question_id={question_id}"
            )

    def consume(
        self,
        callback: Callable[[MQTaskMessage], bool],
        auto_reconnect: bool = True,
    ) -> None:
        """启动消费循环

        支持熔断机制：在连续失败达到阈值后暂停消费。

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
                if isinstance(self.circuit_breaker.state, CircuitOpenState):
                    # 检查是否超过恢复时间
                    if self._circuit_open_time is not None:
                        elapsed = time.time() - self._circuit_open_time
                        if elapsed >= self._recovery_timeout:
                            # 尝试恢复
                            self.circuit_breaker.close()
                            self._circuit_open_time = None
                            logger.info("Circuit breaker recovered after timeout")
                        else:
                            remaining = int(self._recovery_timeout - elapsed)
                            logger.warning(
                                f"Circuit breaker is open, pausing consumption... "
                                f"({remaining}s remaining)"
                            )
                            time.sleep(5)  # 熔断期间每5秒检查一次
                            continue

                    logger.warning(
                        f"Circuit breaker is open, pausing consumption..."
                    )
                    time.sleep(5)
                    continue

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
        _exc_type: Optional[type],
        _exc_val: Optional[BaseException],
        _exc_tb: Optional[object],
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