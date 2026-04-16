"""基础设施层消息模块

提供 RabbitMQ 生产者和消费者功能，用于实现主从 Agent 解耦。

支持两种消费模式：
1. RabbitMQConsumer: 基于协程的异步消费
2. ThreadPoolRabbitMQConsumer: 基于线程池的消费（每个线程独立 channel）
"""

from app.infrastructure.messaging.producer import (
    RabbitMQProducer,
    get_producer,
    AsyncRabbitMQProducer,
)
from app.infrastructure.messaging.consumer import (
    RabbitMQConsumer,
    get_consumer,
    AsyncRabbitMQConsumer,
)
from app.infrastructure.messaging.thread_pool_consumer import (
    ThreadPoolRabbitMQConsumer,
    get_thread_pool_consumer,
)
from app.infrastructure.messaging.message_helper import (
    MQMessageHelper,
    get_mq_message_helper,
)

__all__ = [
    "RabbitMQProducer",
    "get_producer",
    "AsyncRabbitMQProducer",
    "RabbitMQConsumer",
    "get_consumer",
    "AsyncRabbitMQConsumer",
    "ThreadPoolRabbitMQConsumer",
    "get_thread_pool_consumer",
    "MQMessageHelper",
    "get_mq_message_helper",
]