"""RabbitMQ 消息处理工具模块

提供消息重试和死信队列处理的公共方法。
作为基础设施层消息组件，为消费者提供辅助功能。
"""

import aio_pika
from aio_pika.abc import AbstractRobustChannel, AbstractIncomingMessage
from aio_pika import Message, DeliveryMode

from app.infrastructure.config.settings import get_settings
from app.infrastructure.common.logger import logger


class MQMessageHelper:
    """RabbitMQ 消息处理辅助类

    提供消息重试、降级和死信队列处理的公共方法。

    设计原则：
    - 最大重试次数控制
    - 死信队列处理
    - 支持依赖注入
    """

    def __init__(self) -> None:
        """初始化消息处理辅助类"""
        settings = get_settings()
        self._queue = settings.rabbitmq_queue
        self._dlq = settings.rabbitmq_dlq
        self._max_retries = settings.rabbitmq_max_retries

    async def republish_to_back(
        self,
        original_msg: AbstractIncomingMessage,
        channel: AbstractRobustChannel,
        question_id: str,
        retry_count: int,
    ) -> bool:
        """降级：将失败的消息重新发布到队尾

        Args:
            original_msg: 原始消息
            channel: RabbitMQ channel
            question_id: 题目 ID（用于日志）
            retry_count: 当前重试次数

        Returns:
            是否成功重新发布
        """
        new_retry_count = retry_count + 1

        if new_retry_count >= self._max_retries:
            return await self._send_to_dlq(original_msg, channel, question_id)

        try:
            msg = Message(
                body=original_msg.body,
                delivery_mode=DeliveryMode.PERSISTENT,
                headers={"x-retry-count": new_retry_count},
            )
            await channel.default_exchange.publish(msg, routing_key=self._queue)
            logger.info(f"Message republished to back: q_id={question_id}, retry={new_retry_count}")
            return True
        except Exception as e:
            logger.error(f"Failed to republish message: {e}")
            return False

    async def _send_to_dlq(
        self,
        original_msg: AbstractIncomingMessage,
        channel: AbstractRobustChannel,
        question_id: str,
    ) -> bool:
        """死信处理

        Args:
            original_msg: 原始消息
            channel: RabbitMQ channel
            question_id: 题目 ID（用于日志）

        Returns:
            是否成功发送到 DLQ
        """
        try:
            msg = Message(
                body=original_msg.body,
                delivery_mode=DeliveryMode.PERSISTENT,
                headers={"x-dead-letter": True},
            )
            await channel.default_exchange.publish(msg, routing_key=self._dlq)
            logger.warning(f"Message sent to DLQ (max retries exceeded): q_id={question_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
            return False


# 单例获取函数
_mq_message_helper: MQMessageHelper | None = None


def get_mq_message_helper() -> MQMessageHelper:
    """获取 MQ 消息处理辅助类单例

    Returns:
        MQMessageHelper 实例
    """
    global _mq_message_helper
    if _mq_message_helper is None:
        _mq_message_helper = MQMessageHelper()
    return _mq_message_helper


__all__ = [
    "MQMessageHelper",
    "get_mq_message_helper",
]